from __future__ import annotations

from odoo import models
from odoo.tests.common import tagged

from .common import AutomationTestCommon
from odoo.addons.web.controllers.utils import clean_action


@tagged('post_install', '-at_install', 'muk_ai_automation')
class TestRunContract(AutomationTestCommon):
    """Test the server-action return contract of the ``ai_agent`` runners."""

    @classmethod
    def setUpClass(cls) -> None:
        """Add the partner the runners are invoked against."""
        super().setUpClass()
        cls.partner = cls._make_partners(1, prefix='Contract Partner')

    def test_run_result_is_clean_action_safe(self):
        action = self._make_action()
        with self._mock_provider():
            result = action.with_context(
                active_model='res.partner',
                active_id=self.partner.id,
                active_ids=self.partner.ids,
            ).run()
        self.assertNotIsInstance(result, models.BaseModel)
        if result:
            clean_action(result, env=self.env)
        self.assertEqual(len(self._sessions_of(action)), 1)

    def test_run_action_ai_agent_exposes_spawned_ids(self):
        action = self._make_action()
        eval_context = self.env['ir.actions.server']._get_eval_context(action)
        with self._mock_provider():
            action._run_action_ai_agent(eval_context)
        self.assertEqual(
            eval_context['__agent_spawned__'],
            self._sessions_of(action).ids,
        )

    def test_run_action_ai_agent_multi_exposes_every_spawned_id(self):
        partners = self._make_partners(2, prefix='Contract Multi')
        action = self._make_action(
            agent_dispatch_mode='per_record',
            agent_record_domain=self._domain_for(partners),
            agent_max_records_per_fire=100,
        )
        eval_context = self.env['ir.actions.server']._get_eval_context(action)
        with self._mock_provider():
            action._run_action_ai_agent_multi(eval_context)
        spawned = self._sessions_of(action)
        self.assertEqual(len(spawned), 2)
        self.assertEqual(sorted(eval_context['__agent_spawned__']), sorted(spawned.ids))
