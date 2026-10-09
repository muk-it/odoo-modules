from odoo.tests import HttpCase


class TestChatterTour(HttpCase):
    """Drive the AI Sessions box of the chatter on a record linked to a session."""

    def test_muk_ai_chatter_tour(self):
        partner = self.env['res.partner'].create({'name': 'Tour Linked Partner'})
        self.env['muk_ai.session'].create(
            {
                'name': 'Tour Session',
                'state': 'done',
                'user_id': self.env.ref('base.user_admin').id,
                'res_model': 'res.partner',
                'res_id': partner.id,
            }
        )
        self.start_tour(
            f'/odoo/res.partner/{partner.id}', 'muk_ai_chatter_tour', login='admin'
        )
