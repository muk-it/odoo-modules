from __future__ import annotations

from odoo.tests.common import tagged

from .common import AutomationTestCommon
from odoo.addons.muk_ai_automation.tools.dispatch import fire_action


@tagged('post_install', '-at_install', 'muk_ai_automation')
class TestDispatchModes(AutomationTestCommon):
    """Test single and per-record dispatch modes and their caps."""

    @classmethod
    def setUpClass(cls) -> None:
        """Add the partners the per-record dispatch fans out over."""
        super().setUpClass()
        cls.partners = cls._make_partners(5, prefix='Mode Partner')

    def test_single_mode_one_session(self):
        action = self._make_action()
        with self._mock_provider():
            spawned = fire_action(action, {})
        self.assertEqual(len(spawned), 1)

    def test_per_record_mode_one_per_record(self):
        partners = self.partners[:3]
        action = self._make_action(
            agent_dispatch_mode='per_record',
            agent_record_domain=self._domain_for(partners),
            agent_max_records_per_fire=100,
        )
        with self._mock_provider():
            spawned = fire_action(action, {})
        self.assertEqual(len(spawned), 3)
        self.assertEqual(sorted(spawned.mapped('res_id')), sorted(partners.ids))

    def test_per_record_mode_caps_at_max_records_per_fire(self):
        action = self._make_action(
            agent_dispatch_mode='per_record',
            agent_record_domain=self._domain_for(self.partners),
            agent_max_records_per_fire=2,
        )
        with self._mock_provider():
            spawned = fire_action(action, {})
        self.assertEqual(len(spawned), 2)

    def test_per_record_mode_empty_domain_no_sessions(self):
        action = self._make_action(
            agent_dispatch_mode='per_record',
            agent_record_domain="[('id', '=', -1)]",
            agent_max_records_per_fire=100,
        )
        with self._mock_provider():
            spawned = fire_action(action, {})
        self.assertFalse(spawned)

    def test_per_record_mode_malformed_domain_no_sessions(self):
        action = self._make_action(
            agent_dispatch_mode='per_record',
            agent_record_domain="[('id', '=',",
            agent_max_records_per_fire=100,
        )
        with self._mock_provider():
            spawned = fire_action(action, {})
        self.assertFalse(spawned)
