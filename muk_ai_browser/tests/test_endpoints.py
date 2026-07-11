import json
from contextlib import contextmanager
from unittest.mock import MagicMock, patch

from odoo.http import Response

from odoo.addons.muk_ai_browser.controllers import browser as browser_controller
from odoo.addons.muk_ai_browser.tests.common import BrowserTestCommon


class TestEndpoints(BrowserTestCommon):
    """Verify chat and approval routes call the matching session methods."""

    @contextmanager
    def _request(self, body, key):
        fake = MagicMock()
        fake.env = self.env
        fake._mcp_key = key
        fake.get_json_data.return_value = body
        fake.make_json_response.side_effect = lambda data, status=200: Response(
            json.dumps(data), status=status, content_type='application/json'
        )
        with patch.object(browser_controller, 'request', fake):
            yield fake

    def _fixture(self):
        key, _raw = self._device_key()
        ai_session = self._new_ai_session('endpoint')
        browser_session = self._browser_session(ai_session=ai_session, key=key)
        return key, ai_session, browser_session

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

    def test_answer_route_calls_answer(self):
        key, ai_session, browser_session = self._fixture()
        body = {
            'browser_session_id': browser_session.session_id,
            'answer': 'yes please',
        }
        with (
            patch.object(type(ai_session), 'answer', return_value={'ok': 1}) as mock,
            self._request(body, key),
        ):
            browser_controller.BrowserController().answer()
        mock.assert_called_once_with('yes please')

    def test_approve_route_calls_approve_tool(self):
        key, ai_session, browser_session = self._fixture()
        body = {'browser_session_id': browser_session.session_id}
        with (
            patch.object(
                type(ai_session), 'approve_tool', return_value={'ok': 1}
            ) as mock,
            self._request(body, key),
        ):
            browser_controller.BrowserController().approve()
        mock.assert_called_once_with()

    def test_approve_session_route_calls_approve_for_session(self):
        key, ai_session, browser_session = self._fixture()
        body = {'browser_session_id': browser_session.session_id}
        with (
            patch.object(
                type(ai_session), 'approve_for_session', return_value={'ok': 1}
            ) as mock,
            self._request(body, key),
        ):
            browser_controller.BrowserController().approve_session()
        mock.assert_called_once_with()

    def test_reject_approval_route_calls_reject_tool(self):
        key, ai_session, browser_session = self._fixture()
        body = {
            'browser_session_id': browser_session.session_id,
            'reason': 'too risky',
        }
        with (
            patch.object(
                type(ai_session), 'reject_tool', return_value={'ok': 1}
            ) as mock,
            self._request(body, key),
        ):
            browser_controller.BrowserController().reject_approval()
        mock.assert_called_once_with('too risky')

    def test_unknown_browser_session_returns_404(self):
        key, _ai_session, _browser_session = self._fixture()
        body = {'browser_session_id': 'does-not-exist', 'message': 'hi'}
        with self._request(body, key):
            result = browser_controller.BrowserController().message()
        self.assertEqual(result.status_code, 404)

    def test_session_route_creates_named_ai_session(self):
        key, _raw = self._device_key()
        with self._request({'device_label': 'My Laptop'}, key):
            result = browser_controller.BrowserController().session()
        data = json.loads(result.data)
        self.assertTrue(data['browser_session_id'])
        ai_session = self.env['muk_ai.session'].browse(data['ai_session_id'])
        self.assertTrue(ai_session.exists())
        self.assertEqual(ai_session.name, 'My Laptop')
