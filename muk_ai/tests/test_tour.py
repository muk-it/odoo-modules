from odoo.tests import HttpCase, tagged


@tagged('post_install', '-at_install')
class TestChatTour(HttpCase):

    # ----------------------------------------------------------
    # Setup
    # ----------------------------------------------------------

    def setUp(self):
        super().setUp()
        admin = self.env.ref('base.user_admin')
        self.env['muk_ai.session'].sudo().search([
            ('user_id', '=', admin.id),
            ('name', '=', 'Renamed Chat'),
        ]).unlink()

    # ----------------------------------------------------------
    # Tests
    # ----------------------------------------------------------

    def test_chat_tour(self):
        self.start_tour(
            '/odoo/action-muk_ai.action_ai_chat',
            'muk_ai_chat_tour',
            login='admin',
        )
