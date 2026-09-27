import re
from datetime import date, datetime

import vobject

from odoo import Command
from odoo.tests import Form, TransactionCase, new_test_user


class TestResPartner(TransactionCase):
    """Covers name parts, phone numbers, and the vCard export of partners."""

    # ----------------------------------------------------------
    # Tests
    # ----------------------------------------------------------

    def test_the_name_is_composed_from_its_parts(self):
        cases = [
            (('John', 'M', 'Doe'), 'John M Doe'),
            (('John', False, 'Doe'), 'John Doe'),
            ((False, False, 'Doe'), 'Doe'),
        ]
        for (firstname, middlename, lastname), name in cases:
            with self.subTest(name=name):
                partner = self.env['res.partner'].create(
                    {
                        'firstname': firstname,
                        'middlename': middlename,
                        'lastname': lastname,
                    }
                )
                self.assertEqual(partner.name, name)

    def test_a_typed_name_is_split_into_first_and_last_name(self):
        partner = self.env['res.partner'].create(
            {'firstname': 'Old', 'middlename': 'M', 'lastname': 'Name'}
        )
        cases = [
            ('Jane Smith', 'Jane', 'Smith'),
            ('Jane de la Cruz', 'Jane', 'de la Cruz'),
            ('Cher', False, 'Cher'),
        ]
        for name, firstname, lastname in cases:
            with self.subTest(name=name):
                partner.write({'name': name})
                self.assertEqual(partner.firstname, firstname)
                self.assertFalse(partner.middlename)
                self.assertEqual(partner.lastname, lastname)
                self.assertEqual(partner.name, name)

    def test_companies_and_addresses_keep_their_name_whole(self):
        company = self.env['res.partner'].create(
            {'name': 'Acme Inc', 'is_company': True}
        )
        company.write({'name': 'Acme Holding Inc'})
        address = self.env['res.partner'].create(
            {'name': 'Main Warehouse', 'parent_id': company.id, 'type': 'delivery'}
        )
        for partner, name in (
            (company, 'Acme Holding Inc'),
            (address, 'Main Warehouse'),
        ):
            with self.subTest(name=name):
                self.assertFalse(partner.firstname)
                self.assertEqual(partner.lastname, name)
                self.assertEqual(partner.name, name)

    def test_switching_between_company_and_person_splits_the_name_again(self):
        partner = self.env['res.partner'].create({'name': 'Acme Holding Inc'})
        self.assertEqual(partner.firstname, 'Acme')
        partner.write({'is_company': True})
        self.assertEqual(partner.lastname, 'Acme Holding Inc')
        self.assertFalse(partner.firstname)
        partner.write({'is_company': False})
        self.assertEqual(partner.firstname, 'Acme')
        self.assertEqual(partner.lastname, 'Holding Inc')

    def test_a_name_typed_as_company_survives_switching_to_person(self):
        with Form(
            self.env['res.partner'].with_context(default_is_company=True)
        ) as form:
            form.name = 'John Doe'
            form.is_company = False
        self.assertEqual(form.record.name, 'John Doe')
        self.assertEqual(form.record.firstname, 'John')
        self.assertEqual(form.record.lastname, 'Doe')

    def test_formatted_name_follows_the_parent_company(self):
        company = self.env['res.partner'].create({'name': 'OldCo', 'is_company': True})
        child = self.env['res.partner'].create(
            {'parent_id': company.id, 'type': 'invoice', 'street': 'Street 1'}
        )
        self.assertIn('OldCo', child.formatted_name)
        company.name = 'NewCo'
        self.assertIn('NewCo', child.formatted_name)

    def test_birthdate_derives_the_day_month_and_label(self):
        partner = self.env['res.partner'].create(
            {'name': 'Birthday Partner', 'birthdate': date(1990, 5, 1)}
        )
        self.assertEqual(partner.birthdate_day, 1)
        self.assertEqual(partner.birthdate_month, 5)
        self.assertEqual(partner.birthday, 'May 1')
        partner.birthdate = False
        self.assertFalse(partner.birthdate_day)
        self.assertFalse(partner.birthdate_month)
        self.assertFalse(partner.birthday)

    def test_the_mobile_is_primary_and_each_number_shows_itself(self):
        partner = self.env['res.partner'].create(
            {
                'name': 'Two Numbers',
                'phone': '+43 1 5550100',
                'mobile': '+43 664 5550199',
            }
        )
        self.assertEqual(partner.phone_sanitized, '+436645550199')
        self.assertEqual(partner.phone_formatted, '+43 1 5550100')
        self.assertEqual(partner.mobile_sanitized, '+436645550199')
        self.assertEqual(partner.mobile_formatted, '+43 664 5550199')
        partner.phone = False
        self.assertEqual(partner.phone_sanitized, '+436645550199')
        self.assertFalse(partner.phone_formatted)
        found = self.env['res.partner'].search(
            [('phone_mobile_search', 'ilike', '664 5550199')]
        )
        self.assertIn(partner, found)

    def test_the_mobile_is_not_copied_into_an_empty_phone(self):
        partner = self.env['res.partner'].create(
            {'name': 'Copy Guard', 'mobile': '+43 664 5550166'}
        )
        other = self.env['res.partner'].create({'name': 'Other'})
        (partner | other).write(
            {'phone': '+436645550166', 'email': 'guard@example.com'}
        )
        self.assertFalse(partner.phone)
        self.assertEqual(partner.email, 'guard@example.com')
        self.assertEqual(other.phone, '+436645550166')
        partner.write({'phone': '+43 1 5550166'})
        self.assertEqual(partner.phone, '+43 1 5550166')

    def test_a_call_activity_does_not_copy_the_mobile(self):
        partner = self.env['res.partner'].create(
            {'name': 'Call Me', 'mobile': '+43 664 5550155'}
        )
        partner.activity_schedule(
            'mail.mail_activity_data_call', phone='+43664 5550155'
        )
        self.assertFalse(partner.phone)
        other = self.env['res.partner'].create(
            {'name': 'Call Other', 'mobile': '+43 664 5550155'}
        )
        other.activity_schedule('mail.mail_activity_data_call', phone='+43 1 5550100')
        self.assertEqual(other.phone, '+43 1 5550100')

    def test_a_blacklisted_mobile_is_flagged_on_the_mobile(self):
        partner = self.env['res.partner'].create(
            {
                'name': 'Blocked Mobile',
                'phone': '+43 1 5550144',
                'mobile': '+43 664 5550144',
            }
        )
        self.env['phone.blacklist'].sudo().add('+436645550144')
        partner.invalidate_recordset(['mobile_blacklisted', 'phone_blacklisted'])
        self.assertTrue(partner.mobile_blacklisted)
        self.assertFalse(partner.phone_blacklisted)

    def test_build_vcard_exports_the_extended_contact_details(self):
        company = self.env['res.partner'].create(
            {'name': 'Acme Inc', 'is_company': True}
        )
        partner = self.env['res.partner'].create(
            {
                'firstname': 'Dee',
                'middlename': 'Ann',
                'lastname': 'Müller',
                'parent_id': company.id,
                'department': 'Research',
                'street': 'Main 1',
                'street2': 'Floor 3',
                'lang': 'en_US',
                'tz': 'Europe/Vienna',
                'gender': 'f',
                'birthdate': date(1990, 5, 1),
                'nickname': 'Dee',
                'role': 'Maintainer',
                'comment': '<p>Line one</p>',
                'email': 'dee@work.example.com',
                'email2': 'dee@home.example.com',
                'mobile': '+43 664 1234567',
                'phone2': '+43 1 9876543',
                'category_id': [Command.create({'name': 'VIP'})],
            }
        )
        vcard = vobject.readOne(partner._build_vcard().serialize())
        self.assertEqual(
            (vcard.n.value.given, vcard.n.value.additional, vcard.n.value.family),
            ('Dee', 'Ann', 'Müller'),
        )
        self.assertEqual(vcard.fn.value, 'Dee Ann Müller')
        self.assertEqual(vcard.adr.value.extended, 'Floor 3')
        self.assertEqual(vcard.org.value, ['Acme Inc', 'Research'])
        self.assertEqual(
            {
                (line.type_param, line.value)
                for line in vcard.contents['email'] + vcard.contents['tel']
            },
            {
                ('INTERNET', 'dee@work.example.com'),
                ('HOME', 'dee@home.example.com'),
                ('CELL', '+43 664 1234567'),
                ('HOME', '+43 1 9876543'),
            },
        )
        expected = {
            'lang': 'en-US',
            'tz': 'Europe/Vienna',
            'gender': 'F',
            'bday': '19900501',
            'nickname': 'Dee',
            'role': 'Maintainer',
            'note': 'Line one',
            'categories': ['VIP'],
            'kind': 'individual',
        }
        for name, value in expected.items():
            with self.subTest(name=name):
                self.assertEqual(vcard.contents[name][0].value, value)

    def test_build_vcard_describes_a_company_without_an_org(self):
        company = self.env['res.partner'].create(
            {'name': 'Acme Inc', 'department': 'Research'}
        )
        company.write({'is_company': True})
        vcard = vobject.readOne(company._build_vcard().serialize())
        self.assertEqual(vcard.kind.value, 'org')
        self.assertNotIn('org', vcard.contents)

    def test_build_vcard_embeds_the_filled_child_addresses_with_labels(self):
        company = self.env['res.partner'].create(
            {'name': 'Acme Inc', 'is_company': True, 'street': '1 Main St'}
        )
        self.env['res.partner'].create(
            [
                {
                    'name': 'Vienna Office Billing',
                    'parent_id': company.id,
                    'type': 'invoice',
                    'street': '10 Billing Rd',
                    'zip': '12345',
                },
                {
                    'name': 'Acme Inc',
                    'parent_id': company.id,
                    'type': 'delivery',
                    'street': '20 Ship Ave',
                },
                {'parent_id': company.id, 'type': 'other', 'city': 'Side City'},
                {'name': 'Empty Invoice', 'parent_id': company.id, 'type': 'invoice'},
                {'name': 'Jane Doe', 'parent_id': company.id, 'type': 'contact'},
            ]
        )
        serialized = company._build_vcard().serialize()
        labels = dict(re.findall(r'(item\d+)\.X-ABLABEL:([^\r\n]+)', serialized))
        self.assertEqual(
            sorted(labels.values()), ['Delivery', 'Other', 'Vienna Office Billing']
        )
        for group in labels:
            self.assertRegex(serialized, rf'{group}\.ADR;TYPE=WORK:')
        self.assertIn('10 Billing Rd', serialized)
        self.assertIn('20 Ship Ave', serialized)
        self.assertIn('Side City', serialized)

    def test_the_vcard_uid_is_stable_and_needs_no_write_access(self):
        user = new_test_user(self.env, login='vcard_ro', groups='base.group_user')
        partner = self.env['res.partner'].create({'name': 'Jane Doe'})
        self.assertFalse(partner.vcard_uid)
        first = vobject.readOne(partner.with_user(user)._get_vcard_file().decode())
        second = vobject.readOne(partner.with_user(user)._get_vcard_file().decode())
        self.assertTrue(partner.vcard_uid)
        self.assertEqual(first.uid.value, partner.vcard_uid)
        self.assertEqual(second.uid.value, partner.vcard_uid)

    def test_the_vcard_revision_moves_when_exported_data_changes(self):
        stale = datetime(2020, 1, 1)
        company = self.env['res.partner'].create({'name': 'RevCo', 'is_company': True})
        partner = self.env['res.partner'].create(
            {'firstname': 'Rev', 'lastname': 'Partner', 'parent_id': company.id}
        )
        cases = [
            (partner, {'street2': 'Floor 3'}),
            (partner, {'department': 'Research'}),
            (partner, {'mobile': '+43 664 5550111'}),
            (company, {'child_ids': [Command.create({'type': 'other', 'zip': '1'})]}),
        ]
        for record, vals in cases:
            with self.subTest(vals=vals):
                self.env.flush_all()
                self.env.cr.execute(
                    'UPDATE res_partner SET vcard_modified = %s WHERE id = %s',
                    (stale, record.id),
                )
                record.invalidate_recordset(['vcard_modified'])
                record.write(vals)
                self.assertNotEqual(record.vcard_modified, stale)
                self.assertNotIn('REV:2020', record._build_vcard().serialize())
