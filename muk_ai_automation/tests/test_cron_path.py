from __future__ import annotations

from datetime import timedelta

from odoo import fields, models
from odoo.tests.common import tagged

from .common import AutomationTestCommon


@tagged('post_install', '-at_install', 'muk_ai_automation')
class TestCronPath(AutomationTestCommon):
    """Test agent dispatch when a scheduled action is run by the cron runner."""

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    def _make_due_cron(self, action: models.BaseModel) -> models.BaseModel:
        """Create an active cron on ``action`` whose next call is overdue."""
        return self.env['ir.cron'].create(
            {
                'ir_actions_server_id': action.id,
                'interval_type': 'days',
                'interval_number': 1,
                'user_id': self.env.ref('base.user_admin').id,
                'nextcall': fields.Datetime.now() - timedelta(minutes=1),
                'active': True,
            }
        )

    # ----------------------------------------------------------
    # Tests
    # ----------------------------------------------------------

    def test_cron_trigger_spawns_one_session(self):
        action = self._make_action()
        cron = self._make_due_cron(action)
        with self._mock_provider(), self.enter_registry_test_mode():
            cron.method_direct_trigger()
        self.assertEqual(len(self._sessions_of(action)), 1)

    def test_cron_trigger_advances_nextcall(self):
        action = self._make_action()
        cron = self._make_due_cron(action)
        before = cron.nextcall
        with self._mock_provider(), self.enter_registry_test_mode():
            cron.method_direct_trigger()
        cron.invalidate_recordset(['nextcall'])
        self.assertGreater(cron.nextcall, before)
