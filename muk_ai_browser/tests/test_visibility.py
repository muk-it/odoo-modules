from odoo.addons.muk_ai_browser.tests.common import BrowserTestCommon

BROWSER_CLIENT_TOOLS = frozenset(
    {
        'click',
        'fill',
        'hover',
        'navigate',
        'navigate_back',
        'press_key',
        'read_page',
        'screenshot',
        'scroll',
        'select_option',
        'wait_for',
    }
)


class TestVisibility(BrowserTestCommon):
    """Verify client tools are gated on an active browser session."""

    def _client_tool_names(self, session):
        return {
            entry['name']
            for entry in session._get_filtered_catalog()
            if (entry.get('_meta') or {}).get('execute') == 'client'
            and entry['name'] in BROWSER_CLIENT_TOOLS
        }

    def test_client_tools_absent_without_browser_session(self):
        session = self._new_ai_session('no-browser')
        self.assertEqual(self._client_tool_names(session), set())
        self.assertFalse(session._is_client_tool('click'))

    def test_client_tools_present_with_browser_session(self):
        session = self._new_ai_session('with-browser')
        self._browser_session(ai_session=session)
        names = self._client_tool_names(session)
        self.assertIn('click', names)
        self.assertIn('read_page', names)
        self.assertTrue(session._is_client_tool('click'))

    def test_inactive_browser_session_does_not_unlock(self):
        session = self._new_ai_session('inactive')
        browser_session = self._browser_session(ai_session=session)
        browser_session.active = False
        self.assertEqual(self._client_tool_names(session), set())

    def test_client_tools_essential_with_browser_session(self):
        session = self._new_ai_session('essential')
        self._browser_session(ai_session=session)
        essential = session._get_essential_tool_names()
        self.assertIn('read_page', essential)
        self.assertIn('click', essential)

    def test_client_tools_not_essential_without_browser_session(self):
        session = self._new_ai_session('not-essential')
        self.assertNotIn('click', session._get_essential_tool_names())

    def test_webclient_tools_survive_browser_gating(self):
        session = self._new_ai_session('webclient-kind')
        names = {entry['name'] for entry in session._get_filtered_catalog()}
        self.assertIn('adjust_search', names)
        self.assertTrue(session._is_client_tool('adjust_search'))

    def test_webclient_action_not_mirrored_to_extension(self):
        session = self._new_ai_session('routing-webclient')
        browser_session = self._browser_session(ai_session=session)
        session._register_client_action(
            {'call_id': 'c-adj', 'name': 'adjust_search', 'arguments': {}}
        )
        requests = [
            payload
            for event_type, payload in self._browser_events(browser_session)
            if event_type == 'action_request'
        ]
        self.assertEqual(requests, [])

    def test_browser_action_mirrored_to_extension(self):
        session = self._new_ai_session('routing-browser')
        browser_session = self._browser_session(ai_session=session)
        session._register_client_action(
            {'call_id': 'c-read', 'name': 'read_page', 'arguments': {}}
        )
        requests = [
            payload
            for event_type, payload in self._browser_events(browser_session)
            if event_type == 'action_request'
        ]
        self.assertEqual(len(requests), 1)
        self.assertEqual(requests[0]['name'], 'read_page')
