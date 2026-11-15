from __future__ import annotations

import re

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
        query = method == 'GET'
        return self.url_open(
            path,
            params=body if query else None,
            json=None if query else body,
            headers=headers,
            allow_redirects=False,
            method=method,
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

    def _opened(self, path: str = '/ai_browser/chat') -> models.BaseModel:
        """Open the side panel chat at ``path`` and return the chat it shows."""
        url = self.url_open(path).url
        return self.env['muk_ai.session'].browse(int(url.rpartition('=')[2]))

    # ----------------------------------------------------------
    # Tests
    # ----------------------------------------------------------

    def test_a_paired_browser_runs_a_chat_and_only_its_own(self):
        user = new_test_user(self.env, login='browser-a', groups='base.group_user')
        new_test_user(self.env, login='browser-b', groups='base.group_user')
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
        new_test_user(self.env, login='browser-c', groups='base.group_user')
        new_test_user(self.env, login='browser-d', groups='base.group_user')
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
                chat = self.env['muk_ai.session'].search(
                    [('user_id.login', '=', login)]
                )
                self.assertTrue(response.url.endswith(f'/odoo/ai?session_id={chat.id}'))
                self.assertEqual(
                    response.headers.get('Content-Security-Policy'), ancestors
                )
                self.assertEqual(
                    'X-Frame-Options' in response.headers, ancestors is None
                )

    def test_the_side_panel_reopens_the_latest_chat_only_while_it_is_empty(self):
        new_test_user(self.env, login='browser-e', groups='base.group_user')
        self.authenticate('browser-e', 'browser-e')
        first = self._opened()
        self.assertEqual(self._opened(), first)
        first._append_event({'kind': 'user_message', 'content': 'hi'})
        self.assertNotEqual(self._opened(), first)
        self.assertEqual(self._opened(f'/ai_browser/chat/{first.id}'), first)

    def test_only_internal_users_get_a_pairing_code(self):
        new_test_user(self.env, login='browser-portal', groups='base.group_portal')
        self.authenticate('browser-portal', 'browser-portal')
        self.assertEqual(self.url_open('/muk_ai_browser/connect').status_code, 403)
