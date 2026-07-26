from __future__ import annotations

import json
from collections.abc import Iterator
from contextlib import contextmanager
from unittest.mock import MagicMock, patch

from odoo import models
from odoo.http import Response
from odoo.tests.common import new_test_user

from odoo.addons.muk_ai_browser.controllers import browser as browser_controller
from odoo.addons.muk_ai_browser.tests.common import BrowserTestCommon


class TestEndpoints(BrowserTestCommon):
    """Verify the browser routes resolve their session and drive the agent loop."""

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    @contextmanager
    def _request(
        self,
        body: dict | None,
        key: models.BaseModel | None,
        headers: dict | None = None,
        malformed_body: bool = False,
    ) -> Iterator[MagicMock]:
        """Patch the controller request with a fake carrying ``body``."""
        fake = MagicMock()
        fake.env = self.env
        fake._mcp_key = key
        if malformed_body:
            fake.get_json_data.side_effect = ValueError('not json')
        else:
            fake.get_json_data.return_value = body
        fake.httprequest.headers = dict(headers or {})
        fake.make_json_response.side_effect = lambda data, status=200: Response(
            json.dumps(data), status=status, content_type='application/json'
        )
        with patch.object(browser_controller, 'request', fake):
            yield fake

    def _fixture(self) -> tuple[models.BaseModel, ...]:
        """Return a paired ``(key, ai session, browser session)`` triple."""
        key, _raw = self._device_key()
        ai_session = self._new_ai_session('endpoint')
        browser_session = self._browser_session(ai_session=ai_session, key=key)
        return key, ai_session, browser_session

    def _sse_events(self, response: Response) -> list[tuple[str, dict]]:
        """Parse an SSE body into its ``(id, decoded data)`` pairs."""
        events = []
        for block in response.data.decode().split('\n\n'):
            lines = block.split('\n')
            event_id = next(
                (line[4:] for line in lines if line.startswith('id: ')), None
            )
            data = next((line[6:] for line in lines if line.startswith('data: ')), None)
            if data is not None:
                events.append((event_id, json.loads(data)))
        return events

    def _action_requests(self, browser_session: models.BaseModel) -> list:
        """Return the action requests queued for the extension."""
        return [
            payload
            for event_type, payload in self._browser_events(browser_session)
            if event_type == 'action_request'
        ]

    def _gated_fixture(self) -> tuple[models.BaseModel, ...]:
        """Return a fixture parked on a browser-action approval."""
        key, ai_session, browser_session = self._fixture()
        browser_session.last_origin = 'https://shop.example'
        provider = self._script_provider(
            [
                self._tool_payload('click', {'element': 'Buy', 'ref': 'e1'}, 'c0'),
                self._text_payload('Done.'),
            ]
        )
        with provider, self._track_execute([]):
            snapshot = ai_session.start('Click buy.')
        self.assertEqual(snapshot['pending_ask']['kind'], 'approval')
        return key, ai_session, browser_session

    # ----------------------------------------------------------
    # Session
    # ----------------------------------------------------------

    def test_session_route_creates_named_ai_session(self):
        key, _raw = self._device_key()
        with self._request({'device_label': 'My Laptop'}, key):
            result = browser_controller.BrowserController().session()
        data = json.loads(result.data)
        self.assertTrue(data['browser_session_id'])
        ai_session = self.env['muk_ai.session'].browse(data['ai_session_id'])
        self.assertTrue(ai_session.exists())
        self.assertEqual(ai_session.name, 'My Laptop')

    def test_session_route_reattaches_the_same_browser_session(self):
        key, ai_session, browser_session = self._fixture()
        with self._request({'ai_session_id': ai_session.id}, key):
            result = browser_controller.BrowserController().session()
        data = json.loads(result.data)
        self.assertEqual(data['browser_session_id'], browser_session.session_id)
        self.assertEqual(data['ai_session_id'], ai_session.id)

    def test_session_route_refuses_another_users_ai_session(self):
        key, _raw = self._device_key()
        other = new_test_user(self.env, login='endpoint_other')
        victim = self.env['muk_ai.session'].with_user(other).create({'name': 'victim'})
        with self._request({'ai_session_id': victim.id}, key):
            result = browser_controller.BrowserController().session()
        self.assertEqual(result.status_code, 404)
        self.assertEqual(json.loads(result.data), {'error': 'ai_session_not_found'})
        self.assertFalse(
            self.env['muk_ai_browser.session']
            .sudo()
            .search([('ai_session_id', '=', victim.id)]),
        )

    def test_session_route_refuses_a_missing_ai_session(self):
        key, _raw = self._device_key()
        with self._request({'ai_session_id': 99999999}, key):
            result = browser_controller.BrowserController().session()
        self.assertEqual(result.status_code, 404)

    # ----------------------------------------------------------
    # Device isolation
    # ----------------------------------------------------------

    def test_another_device_key_cannot_drive_the_session(self):
        _key, ai_session, browser_session = self._fixture()
        intruder_key, _raw = self._device_key(label='Intruder')
        body = {'browser_session_id': browser_session.session_id, 'message': 'hi'}
        with (
            patch.object(type(ai_session), 'send_message') as mock,
            self._request(body, intruder_key),
        ):
            result = browser_controller.BrowserController().message()
        self.assertEqual(result.status_code, 404)
        mock.assert_not_called()

    def test_archived_browser_session_is_not_resolvable(self):
        key, _ai_session, browser_session = self._fixture()
        browser_session.active = False
        body = {'browser_session_id': browser_session.session_id, 'message': 'hi'}
        with self._request(body, key):
            result = browser_controller.BrowserController().message()
        self.assertEqual(result.status_code, 404)

    def test_unknown_browser_session_returns_404(self):
        key, _ai_session, _browser_session = self._fixture()
        body = {'browser_session_id': 'does-not-exist', 'message': 'hi'}
        with self._request(body, key):
            result = browser_controller.BrowserController().message()
        self.assertEqual(result.status_code, 404)

    def test_malformed_json_body_falls_back_to_route_kwargs(self):
        key, ai_session, browser_session = self._fixture()
        with (
            patch.object(
                type(ai_session), 'send_message', return_value={'ok': 1}
            ) as mock,
            self._request(None, key, malformed_body=True),
        ):
            result = browser_controller.BrowserController().message(
                browser_session_id=browser_session.session_id,
                message='from kwargs',
            )
        self.assertEqual(result.status_code, 200)
        mock.assert_called_once_with('from kwargs')

    # ----------------------------------------------------------
    # Message / result
    # ----------------------------------------------------------

    def test_message_route_sends_message_and_records_origin(self):
        key, ai_session, browser_session = self._fixture()
        body = {
            'browser_session_id': browser_session.session_id,
            'message': 'hello there',
            'origin': 'https://shop.example',
        }
        with (
            patch.object(
                type(ai_session), 'send_message', return_value={'ok': 1}
            ) as mock,
            self._request(body, key),
        ):
            result = browser_controller.BrowserController().message()
        mock.assert_called_once_with('hello there')
        self.assertEqual(browser_session.last_origin, 'https://shop.example')
        self.assertEqual(result.status_code, 200)
        self.assertEqual(json.loads(result.data), {'ok': 1})

    def test_result_route_records_acting_origin(self):
        key, ai_session, browser_session = self._fixture()
        browser_session.last_origin = 'https://app.example'
        body = {
            'browser_session_id': browser_session.session_id,
            'call_id': 'c0',
            'result': {'ok': True},
            'origin': 'https://evil.example',
        }
        with (
            patch.object(
                type(ai_session), 'submit_client_result', return_value={'ok': 1}
            ) as mock,
            self._request(body, key),
        ):
            browser_controller.BrowserController().result()
        mock.assert_called_once_with('c0', {'ok': True})
        self.assertEqual(browser_session.last_origin, 'https://evil.example')

    def test_result_without_origin_keeps_the_previous_one(self):
        key, ai_session, browser_session = self._fixture()
        browser_session.last_origin = 'https://app.example'
        body = {
            'browser_session_id': browser_session.session_id,
            'call_id': 'c0',
            'result': {'ok': True},
        }
        with (
            patch.object(type(ai_session), 'submit_client_result', return_value={}),
            self._request(body, key),
        ):
            browser_controller.BrowserController().result()
        self.assertEqual(browser_session.last_origin, 'https://app.example')

    def test_result_route_completes_a_pending_client_action(self):
        key, ai_session, browser_session = self._fixture()
        browser_session.last_origin = 'https://app.example'
        self.env['muk_ai_browser.permission']._grant(
            ai_session.user_id, 'https://app.example'
        )
        provider = self._script_provider(
            [
                self._tool_payload('click', {'element': 'Open', 'ref': 'e1'}, 'c0'),
                self._text_payload('Clicked.'),
            ]
        )
        with provider, self._track_execute([]):
            ai_session.start('Open the menu.')
            body = {
                'browser_session_id': browser_session.session_id,
                'call_id': 'c0',
                'result': {'ok': True},
            }
            with self._request(body, key):
                response = browser_controller.BrowserController().result()
        snapshot = json.loads(response.data)
        self.assertEqual(snapshot['state'], 'done')
        self.assertEqual(snapshot['last_text'], 'Clicked.')

    def test_reject_route_resumes_the_loop_with_the_rejection(self):
        key, ai_session, browser_session = self._fixture()
        browser_session.last_origin = 'https://app.example'
        self.env['muk_ai_browser.permission']._grant(
            ai_session.user_id, 'https://app.example'
        )
        provider = self._script_provider(
            [
                self._tool_payload('click', {'element': 'Open', 'ref': 'e1'}, 'c0'),
                self._text_payload('Understood.'),
            ]
        )
        with provider, self._track_execute([]):
            ai_session.start('Open the menu.')
            body = {
                'browser_session_id': browser_session.session_id,
                'call_id': 'c0',
                'reason': 'user cancelled',
            }
            with self._request(body, key):
                response = browser_controller.BrowserController().reject()
        snapshot = json.loads(response.data)
        self.assertEqual(snapshot['state'], 'done')

    # ----------------------------------------------------------
    # Approval routes
    # ----------------------------------------------------------

    def test_approve_route_releases_the_action_to_the_extension(self):
        key, _ai_session, browser_session = self._gated_fixture()
        body = {'browser_session_id': browser_session.session_id}
        with self._request(body, key):
            response = browser_controller.BrowserController().approve()
        snapshot = json.loads(response.data)
        self.assertEqual(snapshot['pending_ask']['kind'], 'client_action')
        self.assertEqual(
            [entry['name'] for entry in self._action_requests(browser_session)],
            ['click'],
        )

    def test_approve_session_route_grants_the_origin(self):
        key, ai_session, browser_session = self._gated_fixture()
        body = {'browser_session_id': browser_session.session_id}
        with self._request(body, key):
            browser_controller.BrowserController().approve_session()
        self.assertEqual(
            self.env['muk_ai_browser.permission']._mode_for(
                ai_session.user_id, 'https://shop.example'
            ),
            'follow_plan',
        )

    def test_reject_approval_route_ends_the_turn_without_acting(self):
        key, _ai_session, browser_session = self._gated_fixture()
        body = {
            'browser_session_id': browser_session.session_id,
            'reason': 'too risky',
        }
        provider = self._script_provider([self._text_payload('Stopping.')])
        with provider, self._request(body, key):
            response = browser_controller.BrowserController().reject_approval()
        snapshot = json.loads(response.data)
        self.assertEqual(snapshot['state'], 'done')
        self.assertEqual(self._action_requests(browser_session), [])

    def test_answer_route_answers_a_pending_question(self):
        key, ai_session, browser_session = self._fixture()
        body = {
            'browser_session_id': browser_session.session_id,
            'answer': 'yes please',
        }
        with (
            patch.object(type(ai_session), 'answer', return_value={'ok': 1}) as mock,
            self._request(body, key),
        ):
            result = browser_controller.BrowserController().answer()
        mock.assert_called_once_with('yes please')
        self.assertEqual(json.loads(result.data), {'ok': 1})

    def test_approval_routes_reject_an_unknown_session(self):
        key, _ai_session, _browser_session = self._fixture()
        controller = browser_controller.BrowserController()
        body = {'browser_session_id': 'nope'}
        for route in (
            controller.answer,
            controller.approve,
            controller.approve_session,
            controller.reject_approval,
        ):
            with self._request(body, key):
                self.assertEqual(route().status_code, 404)

    # ----------------------------------------------------------
    # Events stream
    # ----------------------------------------------------------

    def test_events_route_streams_the_queued_events(self):
        key, _ai_session, browser_session = self._fixture()
        browser_session._enqueue_event('state', {'state': 'running'})
        browser_session._enqueue_event('action_request', {'name': 'click'})
        headers = {'X-Browser-Session': browser_session.session_id}
        with self._request({}, key, headers=headers):
            response = browser_controller.BrowserController().events()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers['Content-Type'], 'text/event-stream')
        self.assertTrue(response.data.startswith(b'retry: 10000\n\n'))
        events = self._sse_events(response)
        self.assertEqual([entry[0] for entry in events], ['1', '2'])
        self.assertEqual(events[0][1]['type'], 'state')
        self.assertEqual(events[1][1]['payload'], {'name': 'click'})

    def test_events_route_marks_claimed_events_delivered(self):
        key, _ai_session, browser_session = self._fixture()
        browser_session._enqueue_event('event', {'n': 1})
        headers = {'X-Browser-Session': browser_session.session_id}
        with self._request({}, key, headers=headers):
            browser_controller.BrowserController().events()
        with self._request({}, key, headers=headers):
            response = browser_controller.BrowserController().events()
        self.assertIn(b':heartbeat', response.data)
        self.assertEqual(self._sse_events(response), [])

    def test_events_route_resumes_after_last_event_id(self):
        key, _ai_session, browser_session = self._fixture()
        for index in range(3):
            browser_session._enqueue_event('event', {'n': index})
        headers = {
            'X-Browser-Session': browser_session.session_id,
            'Last-Event-ID': '2',
        }
        with self._request({}, key, headers=headers):
            response = browser_controller.BrowserController().events()
        self.assertEqual(
            [entry[0] for entry in self._sse_events(response)],
            ['3'],
        )

    def test_events_route_ignores_a_malformed_last_event_id(self):
        key, _ai_session, browser_session = self._fixture()
        browser_session._enqueue_event('event', {'n': 0})
        headers = {
            'X-Browser-Session': browser_session.session_id,
            'Last-Event-ID': 'not-a-number',
        }
        with self._request({}, key, headers=headers):
            response = browser_controller.BrowserController().events()
        self.assertEqual([entry[0] for entry in self._sse_events(response)], ['1'])

    def test_events_route_refuses_a_foreign_session(self):
        _key, _ai_session, browser_session = self._fixture()
        intruder_key, _raw = self._device_key(label='Intruder')
        browser_session._enqueue_event('event', {'secret': 'x'})
        headers = {'X-Browser-Session': browser_session.session_id}
        with self._request({}, intruder_key, headers=headers):
            response = browser_controller.BrowserController().events()
        self.assertEqual(response.status_code, 404)

    def test_events_route_without_a_session_header_returns_404(self):
        key, _ai_session, _browser_session = self._fixture()
        with self._request({}, key, headers={}):
            response = browser_controller.BrowserController().events()
        self.assertEqual(response.status_code, 404)

    # ----------------------------------------------------------
    # Pairing handshake
    # ----------------------------------------------------------

    def test_connect_begin_mints_a_code_for_the_caller(self):
        with self._request({}, None):
            result = browser_controller.BrowserController().connect_begin(
                device_label='Laptop',
                scope='read',
            )
        self.assertTrue(result['pairing_code'])
        self.assertEqual(result['expires_in'], 120)
        consumed = self.env['muk_mcp.pairing']._consume(result['pairing_code'])
        self.assertEqual(consumed['user_id'], self.env.uid)
        self.assertEqual(consumed['scope'], 'read')
        self.assertEqual(consumed['device_label'], 'Laptop')

    def test_connect_begin_falls_back_to_write_for_an_unknown_scope(self):
        with self._request({}, None):
            result = browser_controller.BrowserController().connect_begin(
                scope='superuser',
            )
        consumed = self.env['muk_mcp.pairing']._consume(result['pairing_code'])
        self.assertEqual(consumed['scope'], 'write')

    def test_unpair_revokes_the_calling_device_key(self):
        key, _raw = self._device_key()
        with self._request({}, key):
            response = browser_controller.BrowserController().unpair()
        self.assertEqual(json.loads(response.data), {'ok': True})
        key.invalidate_recordset(['active'])
        self.assertFalse(key.active)
