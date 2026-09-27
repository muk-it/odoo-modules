from odoo.tests import Form, TransactionCase


class TestCompanyFlag(TransactionCase):
    """Cover the person or company choice on contacts."""

    # ----------------------------------------------------------
    # Tests
    # ----------------------------------------------------------

    def test_the_flag_overrides_the_tax_id_guess_both_ways(self):
        company, freelancer = self.env['res.partner'].create(
            [
                {'name': 'Flag Company'},
                {'name': 'Flag Freelancer', 'vat': 'BE0477472701'},
            ]
        )
        self.assertFalse(company.is_company)
        self.assertTrue(freelancer.is_company)
        company.write({'is_company': True})
        freelancer.write({'is_company': False})
        self.assertEqual(company.contact_kind, 'company')
        self.assertEqual(freelancer.contact_kind, 'person')

    def test_the_form_shows_the_flag_only_for_top_level_contacts(self):
        company = self.env['res.partner'].create({'name': 'Flag Employer'})
        with Form(self.env['res.partner']) as form:
            form.is_company = True
            form.name = 'Flag Employee'
            self.assertFalse(form._get_modifier('is_company', 'invisible'))
            self.assertTrue(form._get_modifier('function', 'invisible'))
            form.parent_id = company
            self.assertTrue(form._get_modifier('is_company', 'invisible'))
            self.assertFalse(form.is_company)
            self.assertFalse(form._get_modifier('function', 'invisible'))
        self.assertFalse(form.record.is_company)

    def test_a_contact_with_a_parent_is_never_a_company(self):
        partner = self.env['res.partner'].with_context(default_is_company=True)
        company = partner.create({'name': 'Flag Parent'})
        child = partner.create({'name': 'Flag Child', 'parent_id': company.id})
        other = partner.create({'name': 'Flag Other'})
        other.write({'parent_id': company.id})
        self.assertTrue(company.is_company)
        self.assertFalse(child.is_company)
        self.assertFalse(other.is_company)
