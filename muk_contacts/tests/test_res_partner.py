from odoo.exceptions import UserError
from odoo.tests.common import TransactionCase, new_test_user, tagged


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
            f'[{partner.contact_number}]',
            partner.with_context(show_contact_number=True).display_name,
        )

    def test_display_name_stays_plain_without_the_context_flag(self):
        partner = self.env['res.partner'].create({'name': 'Plain Partner'})
        self.assertNotIn(partner.contact_number, partner.display_name)

    def test_generating_a_contact_number_without_a_sequence_raises(self):
        self.env.ref('muk_contacts.sequence_contact_number').active = False
        partner = self.env['res.partner'].create({'name': 'Sequenceless Partner'})
        self.assertFalse(partner.contact_number)
        with self.assertRaises(UserError):
            partner.action_generate_contact_number()

    def test_contact_number_propagates_to_child_contacts_on_rename(self):
        company = self.env['res.partner'].create(
            {'name': 'Propagating Co', 'is_company': True}
        )
        child = self.env['res.partner'].create(
            {'name': 'Propagating Child', 'parent_id': company.id, 'type': 'contact'}
        )
        company.write({'contact_number': 'CN-PROPAGATED'})
        self.assertEqual(child.contact_number, 'CN-PROPAGATED')

    def test_detaching_a_child_with_its_own_number_keeps_it(self):
        company = self.env['res.partner'].create(
            {'name': 'Owner Co', 'is_company': True}
        )
        child = self.env['res.partner'].create(
            {'name': 'Own Number Child', 'parent_id': company.id, 'type': 'contact'}
        )
        child.write({'contact_number': 'CN-OWN'})
        child.write({'parent_id': False})
        child.flush_recordset()
        self.assertEqual(child.contact_number, 'CN-OWN')

    def test_detaching_a_child_honours_an_explicit_contact_number(self):
        company = self.env['res.partner'].create(
            {'name': 'Explicit Co', 'is_company': True}
        )
        child = self.env['res.partner'].create(
            {'name': 'Explicit Child', 'parent_id': company.id, 'type': 'contact'}
        )
        child.write({'parent_id': False, 'contact_number': 'CN-EXPLICIT'})
        child.flush_recordset()
        self.assertEqual(child.contact_number, 'CN-EXPLICIT')

    def test_address_get_ignores_a_default_that_was_not_requested(self):
        partner = self.env['res.partner'].create({'name': 'Partial Request'})
        invoice = self.env['res.partner'].create(
            {'name': 'Invoice Only', 'parent_id': partner.id, 'type': 'invoice'}
        )
        partner.write({'default_invoice_partner_id': invoice.id})
        addresses = partner.address_get(['delivery'])
        self.assertNotEqual(addresses.get('delivery'), invoice.id)
        self.assertEqual(partner.address_get(['invoice'])['invoice'], invoice.id)

    def test_name_search_matches_the_contact_number(self):
        partner = self.env['res.partner'].create({'name': 'Searchable Partner'})
        self.assertTrue(partner.contact_number)
        found = self.env['res.partner'].name_search(partner.contact_number)
        self.assertIn(partner.id, [record_id for record_id, _label in found])

    def test_action_view_partner_opens_the_contact_form(self):
        partner = self.env['res.partner'].create({'name': 'Openable Partner'})
        action = partner.action_view_partner()
        self.assertEqual(action['res_model'], 'res.partner')
        self.assertEqual(action['res_id'], partner.id)
        self.assertEqual(action['name'], partner.name)
        self.assertEqual(
            action['views'], [(self.env.ref('base.view_partner_form').id, 'form')]
        )

    def test_linked_user_exposes_the_user_kind_and_is_searchable(self):
        internal = new_test_user(
            self.env, login='muk_contacts_internal', groups='base.group_user'
        )
        portal = new_test_user(
            self.env, login='muk_contacts_portal', groups='base.group_portal'
        )
        self.assertEqual(internal.partner_id.linked_user_id, internal)
        self.assertEqual(internal.partner_id.linked_user_state, 'internal')
        self.assertEqual(portal.partner_id.linked_user_state, 'portal')
        found = self.env['res.partner'].search([('linked_user_id', '=', internal.id)])
        self.assertIn(internal.partner_id, found)

    def test_linked_user_still_resolves_for_an_archived_user(self):
        user = new_test_user(
            self.env, login='muk_contacts_archived', groups='base.group_user'
        )
        partner = user.partner_id
        user.active = False
        partner.invalidate_recordset(['linked_user_id', 'linked_user_state'])
        self.assertEqual(partner.linked_user_id, user)
        self.assertEqual(partner.linked_user_state, 'internal')

    def test_a_partner_without_a_user_has_no_linked_user_state(self):
        partner = self.env['res.partner'].create({'name': 'Userless Partner'})
        self.assertFalse(partner.linked_user_id)
        self.assertFalse(partner.linked_user_state)
