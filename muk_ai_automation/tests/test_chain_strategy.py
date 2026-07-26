from __future__ import annotations

from odoo import models
from odoo.tests.common import tagged

from .common import AutomationTestCommon
from odoo.addons.muk_ai_automation.tools.dispatch import fire_action


@tagged('post_install', '-at_install', 'muk_ai_automation')
class TestChainStrategy(AutomationTestCommon):
    """Test per-record chaining of sessions across repeated fires."""

    @classmethod
    def setUpClass(cls) -> None:
        """Add the single partner the chained action dispatches over."""
        super().setUpClass()
        cls.partner = cls._make_partners(1, prefix='Chain Partner')

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    def _make_chained_action(self, **vals) -> models.BaseModel:
        """Create a per-record action over the fixture partner."""
        defaults = {
            'agent_dispatch_mode': 'per_record',
            'agent_record_domain': self._domain_for(self.partner),
            'agent_max_records_per_fire': 100,
            'agent_chain_strategy': 'per_record',
        }
        defaults.update(vals)
        return self._make_action(**defaults)

    # ----------------------------------------------------------
    # Tests
    # ----------------------------------------------------------

    def test_chain_per_record_links_previous_session(self):
        action = self._make_chained_action()
        with self._mock_provider():
            first = fire_action(action, {})
        with self._mock_provider():
            second = fire_action(action, {})
        self.assertEqual(len(first), 1)
        self.assertEqual(len(second), 1)
        self.assertEqual(second.previous_session_id, first)

    def test_chain_none_does_not_link_previous(self):
        action = self._make_chained_action(agent_chain_strategy='none')
        with self._mock_provider():
            first = fire_action(action, {})
        with self._mock_provider():
            second = fire_action(action, {})
        self.assertFalse(first.previous_session_id)
        self.assertFalse(second.previous_session_id)

    def test_chain_per_record_with_no_prior_session_leaves_previous_empty(self):
        action = self._make_chained_action()
        with self._mock_provider():
            spawned = fire_action(action, {})
        self.assertEqual(len(spawned), 1)
        self.assertFalse(spawned.previous_session_id)
