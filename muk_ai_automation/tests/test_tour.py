from __future__ import annotations

from odoo import models
from odoo.tests import HttpCase, tagged


@tagged('post_install', '-at_install')
class TestAutomationTour(HttpCase):
    """Drive the AI Sessions chatter box on a record linked to an agent session."""

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    def _make_linked_session(self) -> models.Model:
        """Create a partner and one AI session linked to it via res_model/res_id."""
        partner = self.env['res.partner'].create({'name': 'Tour Linked Partner'})
        self.env['muk_ai.session'].create(
            {
                'name': 'Tour Session',
                'state': 'done',
                'agent_id': self.env.ref('muk_ai.agent_general').id,
                'res_model': 'res.partner',
                'res_id': partner.id,
            }
        )
        return partner

    # ----------------------------------------------------------
    # Tests
    # ----------------------------------------------------------

    def test_muk_ai_automation_tour(self):
        partner = self._make_linked_session()
        self.start_tour(
            f'/odoo/action-base.action_partner_form/{partner.id}',
            'muk_ai_automation_tour',
            login='admin',
        )
