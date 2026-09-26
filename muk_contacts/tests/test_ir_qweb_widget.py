from odoo.tests import TransactionCase


class TestIrQwebWidget(TransactionCase):
    """Cover the contact number and company line of the contact widget."""

    # ----------------------------------------------------------
    # Tests
    # ----------------------------------------------------------

    def test_contact_widget_shows_the_company_and_contact_number(self):
        company = self.env['res.partner'].create({'name': 'Widget Company'})
        contact = self.env['res.partner'].create(
            {'name': 'Widget Contact', 'parent_id': company.id}
        )
        html = self.env['ir.qweb.field.contact'].value_to_html(
            contact, {'fields': ['name', 'contact_number']}
        )
        self.assertIn('>Widget Company<', html)
        self.assertIn('>Widget Contact<', html)
        self.assertNotIn('Widget Company, Widget Contact', html)
        self.assertIn(company.contact_number, html)

    def test_contact_widget_hides_the_contact_number_unless_asked(self):
        partner = self.env['res.partner'].create({'name': 'Widget Partner'})
        html = self.env['ir.qweb.field.contact'].value_to_html(
            partner, {'fields': ['name']}
        )
        self.assertIn('Widget Partner', html)
        self.assertNotIn(partner.contact_number, html)
