from __future__ import annotations

from odoo import models
from odoo.tests.common import TransactionCase, tagged


@tagged('post_install', '-at_install', 'muk_ai_schedule')
class TestScheduleClientKinds(TransactionCase):
    """Verify schedule-spawned sessions drop the webclient client kind."""

    # ----------------------------------------------------------
    # Setup
    # ----------------------------------------------------------

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.agent = cls.env['muk_ai.agent'].create({'name': 'Kinds Agent'})
        cls.schedule = cls.env['muk_ai.schedule'].create(
            {
                'name': 'Kinds Schedule',
                'agent_id': cls.agent.id,
                'prompt': 'Hello.',
                'interval_type': 'days',
                'interval_number': 1,
                'dispatch_mode': 'single',
            }
        )

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    def _make_session(self, **vals) -> models.BaseModel:
        """Create an AI session with the given extra values."""
        return self.env['muk_ai.session'].create({'name': 'Kinds', **vals})

    # ----------------------------------------------------------
    # Tests
    # ----------------------------------------------------------

    def test_interactive_session_keeps_webclient_kind(self):
        session = self._make_session()
        self.assertIn('webclient', session._available_client_kinds())
        names = {entry['name'] for entry in session._get_filtered_catalog()}
        self.assertIn('adjust_search', names)

    def test_scheduled_session_drops_webclient_kind(self):
        session = self._make_session(schedule_id=self.schedule.id)
        self.assertNotIn('webclient', session._available_client_kinds())
        names = {entry['name'] for entry in session._get_filtered_catalog()}
        self.assertNotIn('adjust_search', names)
        self.assertFalse(session._is_client_tool('adjust_search'))
