import re
from datetime import timedelta

from odoo import Command, fields
from odoo.tests.common import TransactionCase, new_test_user, tagged

from odoo.addons.muk_contacts_vcard import _restore_mobile_from_upgrade_notes


@tagged('post_install', '-at_install')
class TestResPartner(TransactionCase):
    """Covers name computation, formatting, and vCard export details."""

    # ----------------------------------------------------------
    # Tests
    # ----------------------------------------------------------

    def test_name_is_computed_from_first_middle_last(self):
        partner = self.env['res.partner'].create({'name': 'Initial Name'})
        partner.write(
            {
                'firstname': 'John',
                'middlename': 'M',
                'lastname': 'Doe',
            }
        )
        self.assertEqual(partner.name, 'John M Doe')

    def test_name_inverse_splits_into_first_and_last(self):
        partner = self.env['res.partner'].create({'name': 'Initial Name'})
        partner.write({'name': 'Jane Smith'})
        self.assertEqual(partner.firstname, 'Jane')
        self.assertEqual(partner.lastname, 'Smith')
        self.assertFalse(partner.middlename)

    def test_formatted_name_can_include_honorific(self):
        prefix = self.env['muk_contacts_vcard.honorific'].create(
            {
                'name': 'Dr.',
                'shortcut': 'Dr.',
                'position': 'preceding',
            }
        )
        suffix = self.env['muk_contacts_vcard.honorific'].create(
            {
                'name': 'PhD',
                'shortcut': 'PhD',
                'position': 'following',
            }
        )
        partner = self.env['res.partner'].create({'name': 'Initial Name'})
        partner.write(
            {
                'firstname': 'John',
                'lastname': 'Doe',
                'honorific_prefix_ids': [Command.set(prefix.ids)],
                'honorific_suffix_ids': [Command.set(suffix.ids)],
            }
        )
        self.assertIn('Dr.', partner.formatted_name)
        self.assertIn('PhD', partner.formatted_name)

    def test_build_vcard_includes_uid_and_home_contacts(self):
        partner = self.env['res.partner'].create({'name': 'Initial Name'})
        partner.write(
            {
                'firstname': 'John',
                'lastname': 'Doe',
                'email': 'john.doe@work.example.com',
                'email2': 'john.doe@home.example.com',
                'phone': '+431234',
                'phone2': '+439876',
                'gender': 'm',
                'birthdate': fields.Date.today() - timedelta(days=1),
                'nickname': 'Johnny',
            }
        )
        self.assertTrue(partner.vcard_modified)
        serialized = partner._build_vcard().serialize()
        self.assertIn('UID:', serialized)
        self.assertIn(partner.vcard_uid, serialized)
        self.assertIn('EMAIL', serialized)
        self.assertIn('TYPE=HOME', serialized)

    def test_build_vcard_includes_mobile_as_cell(self):
        partner = self.env['res.partner'].create(
            {
                'name': 'Mobile Partner',
                'mobile': '+43 664 1234567',
            }
        )
        serialized = partner._build_vcard().serialize()
        self.assertIn('TYPE=CELL', serialized)
        self.assertIn('+43 664 1234567', serialized)

    def test_restore_mobile_from_upgrade_notes(self):
        partner = self.env['res.partner'].create(
            {
                'name': 'Restore Partner',
                'phone': '+43 1 2345678',
            }
        )
        message = self.env['mail.message'].create(
            {
                'model': 'res.partner',
                'res_id': partner.id,
                'message_type': 'notification',
                'body': 'placeholder',
            }
        )
        self.env.flush_all()
        self.env.cr.execute(
            'UPDATE mail_message SET body = %s WHERE id = %s',
            ('Previous Mobile: +43 664 9876543', message.id),
        )
        count = _restore_mobile_from_upgrade_notes(self.env)
        self.assertEqual(count, 1)
        self.assertEqual(partner.mobile, '+43 664 9876543')

    def test_restore_mobile_skips_numbers_already_on_partner(self):
        partner = self.env['res.partner'].create(
            {
                'name': 'Merged Partner',
                'phone': '+43 664 9876543',
            }
        )
        message = self.env['mail.message'].create(
            {
                'model': 'res.partner',
                'res_id': partner.id,
                'message_type': 'notification',
                'body': 'placeholder',
            }
        )
        self.env.flush_all()
        self.env.cr.execute(
            'UPDATE mail_message SET body = %s WHERE id = %s',
            ('Previous Mobile: +43 664 9876543', message.id),
        )
        _restore_mobile_from_upgrade_notes(self.env)
        self.assertFalse(partner.mobile)

    def test_restore_mobile_keeps_existing_mobile(self):
        partner = self.env['res.partner'].create(
            {
                'name': 'Current Partner',
                'mobile': '+43 664 1111111',
            }
        )
        message = self.env['mail.message'].create(
            {
                'model': 'res.partner',
                'res_id': partner.id,
                'message_type': 'notification',
                'body': 'placeholder',
            }
        )
        self.env.flush_all()
        self.env.cr.execute(
            'UPDATE mail_message SET body = %s WHERE id = %s',
            ('Previous Mobile: +43 664 9876543', message.id),
        )
        _restore_mobile_from_upgrade_notes(self.env)
        self.assertEqual(partner.mobile, '+43 664 1111111')

    def test_vcard_export_does_not_require_partner_write_access(self):
        user = new_test_user(self.env, login='vcard_ro', groups='base.group_user')
        partner = self.env['res.partner'].create(
            {
                'firstname': 'Jane',
                'lastname': 'Doe',
            }
        )
        self.assertFalse(partner.vcard_uid)
        content = partner.with_user(user)._get_vcard_file()
        self.assertTrue(content)
        self.assertTrue(partner.vcard_uid)

    def test_formatted_name_recomputes_on_shortcut_change(self):
        honorific = self.env['muk_contacts_vcard.honorific'].create(
            {
                'name': 'Doctor',
                'shortcut': 'Dr.',
                'position': 'preceding',
            }
        )
        partner = self.env['res.partner'].create(
            {
                'firstname': 'John',
                'lastname': 'Doe',
                'honorific_prefix_ids': [Command.set(honorific.ids)],
            }
        )
        self.assertEqual(partner.formatted_name, 'Dr. John Doe')
        honorific.shortcut = 'Dr'
        self.assertIn(
            partner,
            self.env.records_to_compute(partner._fields['vcard_modified']),
        )
        partner.invalidate_recordset(['formatted_name'])
        self.assertEqual(partner.formatted_name, 'Dr John Doe')

    def test_formatted_name_recomputes_on_parent_rename(self):
        company = self.env['res.partner'].create(
            {
                'name': 'OldCo',
                'is_company': True,
            }
        )
        child = self.env['res.partner'].create(
            {
                'parent_id': company.id,
                'type': 'invoice',
                'street': 'Street 1',
            }
        )
        self.assertIn('OldCo', child.formatted_name)
        company.name = 'NewCo'
        child.invalidate_recordset(['formatted_name'])
        self.assertIn('NewCo', child.formatted_name)

    def test_portal_user_can_read_honorific_shortcut(self):
        portal = new_test_user(
            self.env, login='vcard_portal', groups='base.group_portal'
        )
        honorific = self.env['muk_contacts_vcard.honorific'].create(
            {
                'name': 'Doctor',
                'shortcut': 'Dr.',
                'position': 'preceding',
            }
        )
        partner = portal.partner_id.commercial_partner_id
        partner.honorific_prefix_ids = [Command.set(honorific.ids)]
        result = partner.with_user(portal).mapped('honorific_prefix_ids.shortcut')
        self.assertEqual(result, ['Dr.'])

    def test_partner_category_not_readable_by_portal(self):
        portal = new_test_user(
            self.env, login='vcard_portal_cat', groups='base.group_portal'
        )
        self.assertFalse(
            self.env['res.partner.category'].with_user(portal).has_access('read')
        )

    def test_build_vcard_includes_categories_for_internal_user(self):
        category = self.env['res.partner.category'].create({'name': 'VIP'})
        partner = self.env['res.partner'].create(
            {
                'name': 'Tagged Partner',
                'category_id': [Command.set(category.ids)],
            }
        )
        self.assertIn('CATEGORIES', partner._build_vcard().serialize())

    def test_ensure_vcard_uid_sets_uid(self):
        partner = self.env['res.partner'].create({'name': 'Initial Name'})
        partner.write(
            {
                'firstname': 'John',
                'lastname': 'Doe',
                'vcard_uid': False,
            }
        )
        uid = partner._ensure_vcard_uid()
        self.assertTrue(uid)
        self.assertEqual(partner.vcard_uid, uid)

    def test_build_vcard_drops_org_for_company(self):
        company = self.env['res.partner'].create(
            {
                'name': 'Acme Inc',
                'company_type': 'company',
            }
        )
        serialized = company._build_vcard().serialize()
        self.assertNotIn('ORG:', serialized)
        self.assertNotIn('ORG;', serialized)

    def test_build_vcard_keeps_org_for_individual(self):
        company = self.env['res.partner'].create(
            {
                'name': 'Acme Inc',
                'company_type': 'company',
            }
        )
        employee = self.env['res.partner'].create(
            {
                'name': 'Jane Doe',
                'parent_id': company.id,
                'type': 'contact',
            }
        )
        self.assertIn('ORG:Acme Inc', employee._build_vcard().serialize())

    def test_build_vcard_kind_org_for_company(self):
        company = self.env['res.partner'].create(
            {
                'name': 'Acme Inc',
                'company_type': 'company',
            }
        )
        self.assertIn('KIND:org', company._build_vcard().serialize())

    def test_build_vcard_kind_individual_for_contact(self):
        partner = self.env['res.partner'].create(
            {
                'name': 'John Doe',
                'company_type': 'person',
                'type': 'contact',
            }
        )
        self.assertIn('KIND:individual', partner._build_vcard().serialize())

    def test_build_vcard_company_embeds_child_addresses_as_labeled_adr(self):
        company = self.env['res.partner'].create(
            {
                'name': 'Acme Inc',
                'company_type': 'company',
                'street': '1 Main St',
                'city': 'HQ City',
            }
        )
        self.env['res.partner'].create(
            {
                'name': 'Invoice Address',
                'parent_id': company.id,
                'type': 'invoice',
                'street': '10 Billing Rd',
                'city': 'Bill City',
                'zip': '12345',
            }
        )
        self.env['res.partner'].create(
            {
                'name': 'Delivery Address',
                'parent_id': company.id,
                'type': 'delivery',
                'street': '20 Ship Ave',
                'city': 'Ship City',
            }
        )
        self.env['res.partner'].create(
            {
                'name': 'Other Address',
                'parent_id': company.id,
                'type': 'other',
                'street': '30 Side St',
            }
        )
        self.env['res.partner'].create(
            {
                'name': 'Jane Doe',
                'parent_id': company.id,
                'type': 'contact',
            }
        )
        serialized = company._build_vcard().serialize()
        groups = dict(re.findall(r'(item\d+)\.X-ABLABEL:([^\r\n]+)', serialized))
        self.assertEqual(len(groups), 3, msg='expected 3 grouped labels')
        for group, label in groups.items():
            self.assertRegex(
                serialized,
                rf'{group}\.ADR;TYPE=WORK:',
                msg=f'no grouped ADR for {label}',
            )
        self.assertIn('10 Billing Rd', serialized)
        self.assertIn('20 Ship Ave', serialized)
        self.assertIn('30 Side St', serialized)

    def test_build_vcard_uses_child_name_as_label_when_set(self):
        company = self.env['res.partner'].create(
            {
                'name': 'Acme Inc',
                'company_type': 'company',
            }
        )
        self.env['res.partner'].create(
            {
                'name': 'Vienna Office Billing',
                'parent_id': company.id,
                'type': 'invoice',
                'street': '10 Billing Rd',
            }
        )
        self.env['res.partner'].create(
            {
                'name': 'Acme Inc',
                'parent_id': company.id,
                'type': 'delivery',
                'street': '20 Ship Ave',
            }
        )
        serialized = company._build_vcard().serialize()
        self.assertIn('X-ABLABEL:Vienna Office Billing', serialized)
        self.assertNotIn('X-ABLABEL:Acme Inc', serialized)
        self.assertEqual(
            len(re.findall(r'X-ABLABEL:', serialized)),
            2,
            msg='expected 2 labels (custom + delivery fallback)',
        )

    def test_build_vcard_company_skips_empty_child_addresses(self):
        company = self.env['res.partner'].create(
            {
                'name': 'Acme Inc',
                'company_type': 'company',
            }
        )
        self.env['res.partner'].create(
            {
                'name': 'Empty Invoice',
                'parent_id': company.id,
                'type': 'invoice',
            }
        )
        serialized = company._build_vcard().serialize()
        self.assertNotIn('X-ABLABEL', serialized)

    def test_build_vcard_individual_does_not_embed_child_addresses(self):
        company = self.env['res.partner'].create(
            {
                'name': 'Acme Inc',
                'company_type': 'company',
            }
        )
        person = self.env['res.partner'].create(
            {
                'name': 'John Doe',
                'company_type': 'person',
                'type': 'contact',
                'parent_id': company.id,
            }
        )
        self.env['res.partner'].create(
            {
                'name': 'Invoice Address',
                'parent_id': company.id,
                'type': 'invoice',
                'street': '10 Billing Rd',
            }
        )
        serialized = person._build_vcard().serialize()
        self.assertNotIn('X-ABLABEL', serialized)
