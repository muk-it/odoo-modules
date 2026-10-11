from __future__ import annotations

from odoo.tests.common import tagged

from .common import AutomationTestCommon


@tagged('post_install', '-at_install', 'muk_ai_automation')
class TestAutomationClientKinds(AutomationTestCommon):
    """Verify action-spawned sessions drop the webclient client kind."""

    def test_action_spawned_session_drops_webclient_kind(self):
        action = self._make_action()
        session = self.env['muk_ai.session'].create(
            {'name': 'spawned', 'action_server_id': action.id}
        )
        self.assertNotIn('webclient', session._available_client_kinds())
        names = {entry['name'] for entry in session._get_filtered_catalog()}
        self.assertNotIn('adjust_search', names)
