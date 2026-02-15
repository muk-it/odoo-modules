from odoo.tests.common import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestResPartner(TransactionCase):

    # ----------------------------------------------------------
    # Setup
    # ----------------------------------------------------------

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env.ref('muk_contacts.sequence_contact_number').write({
            'active': True,
            'company_id': False,
            'code': 'contact.number',
        })

    def _assert_contact_number_sequence_available(self):
        seq = self.env.ref('muk_contacts.sequence_contact_number')
        next_number = self.env['ir.sequence'].sudo().next_by_code('contact.number')
        self.assertTrue(
            next_number,
            (
                "Sequence 'contact.number' is not available. "
                f"sequence_contact_number: id={seq.id} active={seq.active} "
                f"company_id={seq.company_id.id if seq.company_id else False} code={seq.code}"
            ),
        )

    # ----------------------------------------------------------
    # Tests
    # ----------------------------------------------------------

    def test_contact_number_is_generated_on_create(self):
        self._assert_contact_number_sequence_available()
        partner = self.env['res.partner'].create({
            'name': 'Test Partner'
        })
        self.assertTrue(partner.contact_number)

    def test_contact_number_is_inherited_for_child_contacts(self):
        self._assert_contact_number_sequence_available()
        parent = self.env['res.partner'].create({
            'name': 'Parent Partner'
        })
        child = self.env['res.partner'].create({
            'name': 'Child Partner',
            'parent_id': parent.id,
            'type': 'contact',
        })
        self.assertEqual(child.contact_number, parent.contact_number)

    def test_address_get_respects_default_invoice_delivery(self):
        partner = self.env['res.partner'].create({
            'name': 'Address Partner'
        })
        invoice = self.env['res.partner'].create({
            'name': 'Invoice Address',
            'parent_id': partner.id,
            'type': 'invoice',
        })
        delivery = self.env['res.partner'].create({
            'name': 'Delivery Address',
            'parent_id': partner.id,
            'type': 'delivery',
        })
        partner.write({
            'default_invoice_partner_id': invoice.id,
            'default_delivery_partner_id': delivery.id,
        })
        addresses = partner.address_get(['invoice', 'delivery'])
        self.assertEqual(addresses.get('invoice'), invoice.id)
        self.assertEqual(addresses.get('delivery'), delivery.id)

    def test_display_name_can_include_contact_number(self):
        self._assert_contact_number_sequence_available()
        partner = self.env['res.partner'].create({
            'name': 'Display Partner'
        })
        self.assertTrue(partner.contact_number)
        self.assertIn(
            partner.contact_number,
            partner.with_context(show_contact_number=True).display_name
        )
        partner_formatted = partner.with_context(
            show_contact_number=True,
            formatted_display_name=True,
        )
        self.assertIn(
            f"--[{partner_formatted.contact_number}]--", 
                partner_formatted.display_name
        )
