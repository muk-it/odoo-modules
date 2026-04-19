from odoo.tests import HttpCase, tagged


@tagged('post_install', '-at_install')
class TestPlaygroundTour(HttpCase):

    # ----------------------------------------------------------
    # Tests
    # ----------------------------------------------------------

    def test_playground_tour(self):
        self.start_tour(
            '/odoo/action-muk_mcp.action_mcp_playground',
            'muk_mcp_playground_tour',
            login='admin',
        )
