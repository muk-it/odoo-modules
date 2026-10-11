from __future__ import annotations

from odoo import models
from odoo.tests.common import tagged

from .common import AutomationTestCommon


@tagged('post_install', '-at_install', 'muk_ai_automation')
class TestBaseAutomationPath(AutomationTestCommon):
    """Test agent dispatch triggered through a base automation rule."""

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    def _make_automation(self, action: models.BaseModel) -> models.BaseModel:
        """Create an on-create partner rule running ``action``."""
        return self.env['base.automation'].create(
            {
                'name': 'Run AI on partner create',
                'model_id': self.partner_model.id,
                'trigger': 'on_create',
                'action_server_ids': [(6, 0, [action.id])],
            }
        )

    # ----------------------------------------------------------
    # Tests
    # ----------------------------------------------------------

    def test_on_create_partner_fires_agent_action(self):
        action = self._make_action()
        self._make_automation(action)
        with self._mock_provider():
            partner = self.env['res.partner'].create({'name': 'Trigger Partner'})
        sessions = self._sessions_of(action)
        self.assertEqual(len(sessions), 1)
        self.assertTrue(partner.exists())
