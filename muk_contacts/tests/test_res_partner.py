from odoo.exceptions import UserError
from odoo.tests import TransactionCase, new_test_user


class TestResPartner(TransactionCase):
    """Test contact numbers, address defaults and the linked user of partners."""

    # ----------------------------------------------------------
    # Tests
    # ----------------------------------------------------------

    def test_top_level_partners_are_numbered_and_children_share_the_number(self):
        company, imported = self.env['res.partner'].create(
            [
                {'name': 'Numbered Co'},
                {'name': 'Imported Co', 'contact_number': 'CN-IMPORTED'},
            ]
        )
        child = self.env['res.partner'].create(
            {'name': 'Numbered Child', 'parent_id': company.id}
        )
        self.assertTrue(company.contact_number)
        self.assertEqual(imported.contact_number, 'CN-IMPORTED')
        self.assertEqual(child.contact_number, company.contact_number)
        company.write({'contact_number': 'CN-RENUMBERED'})
        self.assertEqual(child.contact_number, 'CN-RENUMBERED')

    def test_generating_a_contact_number_needs_the_sequence(self):
        sequence = self.env.ref('muk_contacts.sequence_contact_number')
        sequence.active = False
        partner = self.env['res.partner'].create({'name': 'Sequenceless Partner'})
        self.assertFalse(partner.contact_number)
        with self.assertRaises(UserError):
            partner.action_generate_contact_number()
        sequence.active = True
        partner.action_generate_contact_number()
        self.assertTrue(partner.contact_number)

    def test_detaching_a_child_renumbers_it_only_when_it_shares_the_number(self):
        company = self.env['res.partner'].create({'name': 'Detach Co'})
        shared, own, explicit = self.env['res.partner'].create(
            [
                {'name': name, 'parent_id': company.id}
                for name in ('Shared Child', 'Own Child', 'Explicit Child')
            ]
        )
        own.write({'contact_number': 'CN-OWN'})
        (shared | own).write({'parent_id': False})
        explicit.write({'parent_id': False, 'contact_number': 'CN-EXPLICIT'})
        self.env.flush_all()
        self.assertTrue(shared.contact_number)
        self.assertNotEqual(shared.contact_number, company.contact_number)
        self.assertEqual(own.contact_number, 'CN-OWN')
        self.assertEqual(explicit.contact_number, 'CN-EXPLICIT')

    def test_address_get_prefers_the_configured_defaults(self):
        partner = self.env['res.partner'].create({'name': 'Address Partner'})
        _first_invoice, invoice, _first_delivery, delivery = self.env[
            'res.partner'
        ].create(
            [
                {'name': name, 'parent_id': partner.id, 'type': kind}
                for name, kind in (
                    ('A Invoice', 'invoice'),
                    ('B Invoice', 'invoice'),
                    ('A Delivery', 'delivery'),
                    ('B Delivery', 'delivery'),
                )
            ]
        )
        partner.write(
            {
                'default_invoice_partner_id': invoice.id,
                'default_delivery_partner_id': delivery.id,
            }
        )
        addresses = partner.address_get(['invoice', 'delivery'])
        self.assertEqual(addresses['invoice'], invoice.id)
        self.assertEqual(addresses['delivery'], delivery.id)
        self.assertNotIn('invoice', partner.address_get(['delivery']))

    def test_display_name_shows_the_contact_number_only_on_request(self):
        partner = self.env['res.partner'].create(
            {'name': 'Named Partner', 'contact_number': 'CN-NAME'}
        )
        self.assertEqual(partner.display_name, 'Named Partner')
        shown = partner.with_context(show_contact_number=True)
        self.assertEqual(shown.display_name, '[CN-NAME] Named Partner')
        formatted = shown.with_context(formatted_display_name=True)
        self.assertEqual(formatted.display_name, '--[CN-NAME]-- Named Partner')

    def test_name_search_matches_the_contact_number(self):
        partner = self.env['res.partner'].create(
            {'name': 'Searchable Partner', 'contact_number': 'CN-SEARCH'}
        )
        found = self.env['res.partner'].name_search('CN-SEARCH')
        self.assertEqual([record_id for record_id, _label in found], [partner.id])

    def test_contact_kind_tells_companies_persons_and_addresses_apart(self):
        company = self.env['res.partner'].create(
            {'name': 'Kind Company', 'vat': 'BE0477472701'}
        )
        person, delivery = self.env['res.partner'].create(
            [
                {'name': 'Kind Person', 'parent_id': company.id},
                {'name': 'Kind Delivery', 'parent_id': company.id, 'type': 'delivery'},
            ]
        )
        self.assertEqual(company.contact_kind, 'company')
        self.assertEqual(person.contact_kind, 'person')
        self.assertEqual(delivery.contact_kind, 'delivery')

    def test_linked_user_exposes_the_user_kind_and_is_searchable(self):
        internal = new_test_user(
            self.env, login='muk_contacts_internal', groups='base.group_user'
        )
        portal = new_test_user(
            self.env, login='muk_contacts_portal', groups='base.group_portal'
        )
        userless = self.env['res.partner'].create({'name': 'Userless Partner'})
        self.assertEqual(internal.partner_id.linked_user_id, internal)
        self.assertEqual(internal.partner_id.linked_user_state, 'internal')
        self.assertEqual(portal.partner_id.linked_user_state, 'portal')
        self.assertFalse(userless.linked_user_state)
        found = self.env['res.partner'].search([('linked_user_id', '=', internal.id)])
        self.assertEqual(found, internal.partner_id)

    def test_linked_user_still_resolves_for_an_archived_user(self):
        user = new_test_user(
            self.env, login='muk_contacts_archived', groups='base.group_user'
        )
        partner = user.partner_id
        user.active = False
        partner.invalidate_recordset(['linked_user_id', 'linked_user_state'])
        self.assertEqual(partner.linked_user_id, user)
        self.assertEqual(partner.linked_user_state, 'internal')

    def test_merging_a_numbered_partner_into_an_unnumbered_one(self):
        sequence = self.env.ref('muk_contacts.sequence_contact_number')
        sequence.active = False
        dst = self.env['res.partner'].create(
            {'name': 'Legacy Partner', 'email': 'dup@example.com'}
        )
        sequence.active = True
        src = self.env['res.partner'].create(
            {'name': 'New Duplicate', 'email': 'dup@example.com'}
        )
        number = src.contact_number
        wizard = self.env['base.partner.merge.automatic.wizard'].create({})
        wizard._merge([src.id, dst.id], dst)
        self.assertFalse(src.exists())
        self.assertEqual(dst.contact_number, number)
