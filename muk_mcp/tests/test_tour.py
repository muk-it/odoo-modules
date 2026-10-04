from odoo.tests import HttpCase


class TestPlaygroundTour(HttpCase):
    """Run the MCP playground browser tour end to end."""

    # ----------------------------------------------------------
    # Tests
    # ----------------------------------------------------------

    def test_playground_tour(self):
        self.start_tour(
            '/odoo/mcp-playground', 'muk_mcp_playground_tour', login='admin'
        )
