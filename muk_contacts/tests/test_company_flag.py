from odoo.tests import Form, TransactionCase


class TestCompanyFlag(TransactionCase):
    """Cover the person or company choice on contacts."""

    # ----------------------------------------------------------
    # Tests
    # ----------------------------------------------------------

    def test_a_contact_without_tax_id_can_be_marked_as_company(self):
        partner = self.env['res.partner'].create({'name': 'Flag Company'})
        self.assertFalse(partner.is_company)
        partner.write({'is_company': True})
        self.assertTrue(partner.is_company)
        self.assertEqual(partner.contact_kind, 'company')

    def test_a_contact_with_tax_id_can_be_marked_as_person(self):
        partner = self.env['res.partner'].create(
            {'name': 'Flag Freelancer', 'vat': 'BE0477472701'}
        )
        self.assertTrue(partner.is_company)
        partner.write({'is_company': False})
        self.assertFalse(partner.is_company)
        self.assertEqual(partner.contact_kind, 'person')

    def test_the_form_shows_the_flag_only_for_top_level_contacts(self):
        company = self.env['res.partner'].create({'name': 'Flag Employer'})
        with Form(self.env['res.partner']) as form:
            form.name = 'Flag Employee'
            form.is_company = True
            self.assertFalse(form._get_modifier('is_company', 'invisible'))
            self.assertTrue(form._get_modifier('function', 'invisible'))
            form.parent_id = company
            self.assertTrue(form._get_modifier('is_company', 'invisible'))
            self.assertFalse(form.is_company)
            self.assertFalse(form._get_modifier('function', 'invisible'))
        self.assertFalse(form.record.is_company)
