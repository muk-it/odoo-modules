from __future__ import annotations

from odoo import models
from odoo.tests import HttpCase, tagged


@tagged('post_install', '-at_install')
class TestScheduleTour(HttpCase):
    """Drive the schedule kanban + form and its countdown widget through the web client."""

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    def _make_schedule(self) -> models.Model:
        """Create one active daily schedule for the tour to open."""
        return self.env['muk_ai.schedule'].create(
            {
                'name': 'Tour Digest',
                'agent_id': self.env.ref('muk_ai.agent_general').id,
                'prompt': 'Summarize today.',
                'interval_type': 'days',
                'interval_number': 1,
                'dispatch_mode': 'single',
            }
        )

    # ----------------------------------------------------------
    # Tests
    # ----------------------------------------------------------

    def test_muk_ai_schedule_tour(self):
        self._make_schedule()
        self.start_tour('/odoo/ai-schedules', 'muk_ai_schedule_tour', login='admin')
