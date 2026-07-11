from odoo.addons.muk_ai_browser.tests.common import (
    BROWSER_TOOL_NAMES,
    BrowserTestCommon,
)


class TestBrowserTools(BrowserTestCommon):
    """Verify the browser tools are registered and detected as client tools."""

    def test_all_tools_registered_with_client_meta(self):
        catalog = self.env['muk_mcp.tool'].get_tools(registry='odoo')
        by_name = {entry['name']: entry for entry in catalog}
        for name in BROWSER_TOOL_NAMES:
            self.assertIn(name, by_name)
            self.assertEqual(
                (by_name[name].get('_meta') or {}).get('execute'),
                'client',
            )

    def test_session_detects_client_tools(self):
        session = self._new_ai_session('detect')
        self._browser_session(ai_session=session)
        for name in BROWSER_TOOL_NAMES:
            self.assertTrue(
                session._is_client_tool(name),
                f'{name} should be a client tool',
            )

    def test_tool_categories(self):
        catalog = self.env['muk_mcp.tool'].get_playground_tools()
        by_name = {entry['name']: entry for entry in catalog}
        write_tools = {
            'click',
            'fill',
            'select_option',
            'press_key',
            'navigate',
            'navigate_back',
        }
        for name in write_tools:
            self.assertEqual(by_name[name]['category'], 'write')
        for name in set(BROWSER_TOOL_NAMES) - write_tools:
            self.assertEqual(by_name[name]['category'], 'read')
