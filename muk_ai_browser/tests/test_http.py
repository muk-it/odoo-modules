from __future__ import annotations

import re
from urllib.parse import urlsplit

from requests import Response

from odoo import models
from odoo.tests import HttpCase, new_test_user, tagged


@tagged('post_install', '-at_install')
class TestHttp(HttpCase):
    """Drive the extension contract: pair, attach, poll, frame the chat, unpair."""

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    def _call(
        self,
        path: str,
        key: str | None,
        body: dict | None = None,
        method: str = 'POST',
        headers: dict | None = None,
    ) -> Response:
        """Call an extension route with ``key`` as bearer, ``body`` as JSON or query."""
        headers = {
            **(headers or {}),
            **({'Authorization': f'Bearer {key}'} if key else {}),
        }
        if method == 'GET':
            return self.opener.get(
                self.base_url() + path,
                params=body,
                headers=headers,
                allow_redirects=False,
                timeout=12,
            )
        return self.opener.post(
            self.base_url() + path,
            json=body,
            headers=headers,
            allow_redirects=False,
            timeout=12,
        )

    def _pair(self, login: str) -> str:
        """Pair a browser for ``login`` through the connect page and return its key."""
        self.authenticate(login, login)
        page = self.url_open('/muk_ai_browser/connect').text
        code = re.search(r'name="muk-ai-browser-pairing" content="([^"]+)"', page)[1]
        self.authenticate(None, None)
        paired = self._call(
            '/muk_ai_browser/pair',
            None,
            {'pairing_code': code},
            headers={'Origin': f'chrome-extension://{login}'},
        )
        self.assertEqual(paired.status_code, 200)
        reused = self._call('/muk_ai_browser/pair', None, {'pairing_code': code})
        self.assertEqual(reused.status_code, 400)
        return paired.json()['api_key']

    def _user(self, login: str, group: str = 'base.group_user') -> models.BaseModel:
        """Create a user in ``group`` who signs in with the login as password."""
        return new_test_user(self.env, login=login, password=login, groups=group)

    def _opened(self, path: str = '/ai_browser/chat') -> models.BaseModel:
        """Open the side panel chat at ``path`` and return the chat it shows."""
        response = self.url_open(path)
        location = response.history[0].headers['Location']
        self.assertIn('/web#action=muk_ai.chat&session_id=', location)
        return self.env['muk_ai.session'].browse(int(location.rpartition('=')[2]))

    # ----------------------------------------------------------
    # Tests
    # ----------------------------------------------------------

    def test_a_paired_browser_runs_a_chat_and_only_its_own(self):
        user = self._user('browser-a')
        self._user('browser-b')
        key, other = self._pair('browser-a'), self._pair('browser-b')
        self.assertEqual(
            self._call('/muk_ai_browser/whoami', key, method='GET').json()['id'],
            user.id,
        )
        attached = self._call(
            '/muk_ai_browser/session', key, {'device_label': 'Chrome'}
        ).json()
        chat_id = attached['browser_session_id']
        poll = self._call(
            '/muk_ai_browser/events',
            key,
            {'browser_session_id': chat_id, 'origin': 'https://x.example.com/p'},
            'GET',
        ).json()
        self.assertEqual(
            poll, {'state': 'new', 'actions': [], 'plan_origins': [], 'retry_ms': 5000}
        )
        for label, path, token, body, status in (
            (
                'foreign key',
                '/muk_ai_browser/events',
                other,
                {'browser_session_id': chat_id},
                404,
            ),
            (
                'foreign chat',
                '/muk_ai_browser/session',
                other,
                {'ai_session_id': int(chat_id)},
                404,
            ),
            (
                'no key',
                '/muk_ai_browser/events',
                None,
                {'browser_session_id': chat_id},
                401,
            ),
            ('the key is no MCP key', '/mcp', key, None, 401),
            (
                'no pending call',
                '/muk_ai_browser/result',
                key,
                {'browser_session_id': chat_id, 'call_id': 'c0', 'result': {}},
                409,
            ),
        ):
            with self.subTest(label):
                method = 'GET' if path.endswith('events') else 'POST'
                self.assertEqual(
                    self._call(path, token, body, method).status_code, status
                )
        chat = self.env['muk_ai.session'].browse(int(chat_id))
        self.assertEqual(chat.browser_origin, 'https://x.example.com')
        self.assertTrue(chat._browser_attached())
        self.assertEqual(self._call('/muk_ai_browser/unpair', key).status_code, 200)
        self.assertEqual(
            self._call('/muk_ai_browser/whoami', key, method='GET').status_code, 401
        )

    def test_only_the_users_paired_extension_may_frame_the_chat(self):
        self._user('browser-c')
        self._user('browser-d')
        self._pair('browser-c')
        self._pair('browser-c')
        self.assertEqual(
            self.env['muk_mcp.key'].search_count(
                [('browser', '=', True), ('user_id.login', '=', 'browser-c')]
            ),
            1,
        )
        for login, ancestors in (
            ('browser-c', "frame-ancestors 'self' chrome-extension://browser-c"),
            ('browser-d', None),
        ):
            with self.subTest(login=login):
                self.authenticate(login, login)
                response = self.url_open('/ai_browser/chat')
                self.assertEqual(urlsplit(response.url).path, '/web')
                self.assertEqual(
                    response.headers.get('Content-Security-Policy'), ancestors
                )
                self.assertEqual(
                    'X-Frame-Options' in response.headers, ancestors is None
                )

    def test_the_side_panel_reopens_the_latest_chat_only_while_it_is_empty(self):
        self._user('browser-e')
        self.authenticate('browser-e', 'browser-e')
        first = self._opened()
        self.assertEqual(self._opened(), first)
        first._append_event({'kind': 'user_message', 'content': 'hi'})
        self.assertNotEqual(self._opened(), first)
        self.assertEqual(self._opened(f'/ai_browser/chat/{first.id}'), first)

    def test_only_internal_users_get_a_pairing_code(self):
        self._user('browser-portal', 'base.group_portal')
        self.authenticate('browser-portal', 'browser-portal')
        self.assertEqual(self.url_open('/muk_ai_browser/connect').status_code, 403)

    def test_the_browser_reads_the_card_reports_tabs_and_fetches_only_an_upload(self):
        user = self._user('browser-f')
        key = self._pair('browser-f')
        chat_id = self._call('/muk_ai_browser/session', key, {}).json()[
            'browser_session_id'
        ]
        self.env['res.partner'].create(
            {'name': 'Shop', 'website': 'shop.card-test.org'}
        )
        card = self._call(
            '/muk_ai_browser/card', key, {'url': 'https://shop.card-test.org/p'}, 'GET'
        )
        self.assertEqual(card.json()['partner']['name'], 'Shop')
        self.assertEqual(
            self._call('/muk_ai_browser/card', None, {'url': 'x'}, 'GET').status_code,
            401,
        )
        tabs = '[{"id": 4, "origin": "https://Shop.example.com/a"}, {"id": "x"}]'
        self._call(
            '/muk_ai_browser/events',
            key,
            {'browser_session_id': chat_id, 'tabs': tabs},
            'GET',
        )
        chat = self.env['muk_ai.session'].browse(int(chat_id))
        self.assertEqual(
            chat.browser_key_id.browser_tabs,
            [{'id': 4, 'origin': 'https://shop.example.com'}],
        )
        attachment = (
            self.env['ir.attachment']
            .with_user(user)
            .create({'name': 'Quote.pdf', 'raw': b'%PDF quote'})
        )
        hidden = self.env['ir.attachment'].create(
            {
                'name': 'Secret.pdf',
                'raw': b'%PDF secret',
                'res_model': 'ir.config_parameter',
                'res_id': self.env['ir.config_parameter'].search([], limit=1).id,
            }
        )
        chat.pending_ask = {
            'kind': 'client_action',
            'actions': [
                {
                    'call_id': 'c1',
                    'name': 'browser_upload_file',
                    'arguments': {'attachment_id': attachment.id},
                },
                {
                    'call_id': 'c2',
                    'name': 'browser_click',
                    'arguments': {'attachment_id': attachment.id},
                },
                {
                    'call_id': 'c4',
                    'name': 'browser_upload_file',
                    'arguments': {'attachment_id': hidden.id},
                },
            ],
        }
        responses = {
            call_id: self._call(
                '/muk_ai_browser/file',
                key,
                {'browser_session_id': chat_id, 'call_id': call_id},
                'GET',
            )
            for call_id in ('c1', 'c2', 'c3', 'c4')
        }
        self.assertEqual(
            [response.status_code for response in responses.values()],
            [200, 404, 404, 404],
        )
        self.assertEqual(responses['c1'].content, b'%PDF quote')
        self.assertIn('Quote.pdf', responses['c1'].headers['Content-Disposition'])
