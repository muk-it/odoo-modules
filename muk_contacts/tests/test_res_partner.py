from odoo.tests.common import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestResPartner(TransactionCase):
    """Test contact number generation and address default resolution."""

    # ----------------------------------------------------------
    # Tests
    # ----------------------------------------------------------

    def test_contact_number_is_generated_on_action(self):
        partner = self.env['res.partner'].create(
            {
                'contact_number': False,
                'name': 'Test Partner',
            }
        )
        partner.action_generate_contact_number()
        self.assertTrue(partner.contact_number)

    def test_contact_number_is_generated_on_create(self):
        partner = self.env['res.partner'].create(
            {
                'contact_number': False,
                'name': 'Test Partner',
                'parent_id': False,
            }
        )
        self.assertTrue(partner.contact_number)

    def test_contact_number_is_inherited_for_child_contacts(self):
        parent = self.env['res.partner'].create(
            {
                'contact_number': False,
                'name': 'Parent Partner',
                'parent_id': False,
            }
        )
        child = self.env['res.partner'].create(
            {
                'contact_number': False,
                'name': 'Child Partner',
                'parent_id': parent.id,
                'type': 'contact',
            }
        )
        self.assertEqual(child.contact_number, parent.contact_number)

    def test_detaching_child_does_not_collide_on_contact_number(self):
        company = self.env['res.partner'].create(
            {
                'name': 'Company Partner',
                'is_company': True,
            }
        )
        self.assertTrue(company.contact_number)
        child = self.env['res.partner'].create(
            {
                'name': 'Child Partner',
                'parent_id': company.id,
                'type': 'contact',
            }
        )
        self.assertEqual(child.contact_number, company.contact_number)
        child.write({'parent_id': False})
        child.flush_recordset()
        self.assertTrue(child.contact_number)
        self.assertNotEqual(child.contact_number, company.contact_number)

    def test_detaching_company_child_keeps_own_contact_number(self):
        holding = self.env['res.partner'].create(
            {
                'name': 'Holding',
                'is_company': True,
            }
        )
        sub = self.env['res.partner'].create(
            {
                'name': 'Sub',
                'is_company': True,
            }
        )
        original = sub.contact_number
        self.assertTrue(original)
        sub.write({'parent_id': holding.id})
        self.assertEqual(sub.contact_number, original)
        sub.write({'parent_id': False})
        sub.flush_recordset()
        self.assertEqual(sub.contact_number, original)

    def test_address_get_respects_default_invoice_delivery(self):
        partner = self.env['res.partner'].create({'name': 'Address Partner'})
        invoice = self.env['res.partner'].create(
            {
                'name': 'Invoice Address',
                'parent_id': partner.id,
                'type': 'invoice',
            }
        )
        delivery = self.env['res.partner'].create(
            {
                'name': 'Delivery Address',
                'parent_id': partner.id,
                'type': 'delivery',
            }
        )
        partner.write(
            {
                'default_invoice_partner_id': invoice.id,
                'default_delivery_partner_id': delivery.id,
            }
        )
        addresses = partner.address_get(['invoice', 'delivery'])
        self.assertEqual(addresses.get('invoice'), invoice.id)
        self.assertEqual(addresses.get('delivery'), delivery.id)

    def test_display_name_can_include_contact_number(self):
        partner = self.env['res.partner'].create(
            {
                'contact_number': False,
                'name': 'Test Partner',
                'parent_id': False,
            }
        )
        self.assertTrue(partner.contact_number)
        self.assertIn(
            partner.contact_number,
            partner.with_context(show_contact_number=True).display_name,
        )
        partner_formatted = partner.with_context(
            show_contact_number=True,
            formatted_display_name=True,
        )
        self.assertIn(
            f'--[{partner_formatted.contact_number}]--', partner_formatted.display_name
        )
