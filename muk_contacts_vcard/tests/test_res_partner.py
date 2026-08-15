from __future__ import annotations

import base64
import os
import re
from datetime import date, datetime, timedelta
from io import BytesIO

import vobject
from PIL import Image

from odoo import Command, fields
from odoo.tests.common import TransactionCase, new_test_user, tagged

from odoo.addons.muk_contacts_vcard import _restore_mobile_from_upgrade_notes


def _noise_png(size: int = 256) -> bytes:
    """Return an incompressible PNG image of ``size`` pixels for binary tests."""
    buffer = BytesIO()
    image = Image.frombytes('RGB', (size, size), os.urandom(size * size * 3))
    image.save(buffer, format='PNG')
    return buffer.getvalue()


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

    def test_vcard_modified_bumps_on_street2(self):
        stale = datetime(2020, 1, 1, 0, 0, 0)
        partner = self.env['res.partner'].create(
            {
                'firstname': 'Rev',
                'lastname': 'Partner',
                'street': 'Main 1',
            }
        )
        self.env.flush_all()
        self.env.cr.execute(
            'UPDATE res_partner SET vcard_modified = %s WHERE id = %s',
            (stale, partner.id),
        )
        partner.invalidate_recordset(['vcard_modified'])
        self.assertEqual(partner.vcard_modified, stale)
        partner.write({'street2': 'Floor 3'})
        self.env.flush_all()
        partner.invalidate_recordset(['vcard_modified'])
        self.assertNotEqual(partner.vcard_modified, stale)

    def test_vcard_modified_bumps_on_department(self):
        stale = datetime(2020, 1, 1, 0, 0, 0)
        company = self.env['res.partner'].create({'name': 'RevCo', 'is_company': True})
        employee = self.env['res.partner'].create(
            {
                'firstname': 'Emp',
                'lastname': 'Loyee',
                'parent_id': company.id,
                'type': 'contact',
            }
        )
        self.env.flush_all()
        self.env.cr.execute(
            'UPDATE res_partner SET vcard_modified = %s WHERE id = %s',
            (stale, employee.id),
        )
        employee.invalidate_recordset(['vcard_modified'])
        self.assertEqual(employee.vcard_modified, stale)
        employee.write({'department': 'Research'})
        self.env.flush_all()
        employee.invalidate_recordset(['vcard_modified'])
        self.assertNotEqual(employee.vcard_modified, stale)

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

    def test_build_name_joins_only_the_filled_parts(self):
        model = self.env['res.partner']
        self.assertEqual(model._build_name('John', 'M', 'Doe'), 'John M Doe')
        self.assertEqual(model._build_name('John', False, 'Doe'), 'John Doe')
        self.assertEqual(model._build_name(False, False, 'Doe'), 'Doe')
        self.assertEqual(model._build_name(False, False, False), '')

    def test_split_name_keeps_compound_last_names_together(self):
        model = self.env['res.partner']
        self.assertEqual(model._split_name('Jane Smith'), ('Smith', 'Jane'))
        self.assertEqual(model._split_name('Jane de la Cruz'), ('de la Cruz', 'Jane'))
        self.assertEqual(model._split_name('Cher'), ('Cher', False))
        self.assertEqual(model._split_name(''), (False, False))
        self.assertEqual(
            model._split_name('Acme Holding Inc', is_company=True),
            ('Acme Holding Inc', False),
        )

    def test_renaming_a_company_never_splits_off_a_first_name(self):
        company = self.env['res.partner'].create(
            {'name': 'Acme Inc', 'is_company': True}
        )
        company.write({'name': 'Acme Holding Inc'})
        self.assertEqual(company.lastname, 'Acme Holding Inc')
        self.assertFalse(company.firstname)
        self.assertEqual(company.name, 'Acme Holding Inc')

    def test_unicode_name_parts_round_trip_through_the_vcard(self):
        partner = self.env['res.partner'].create(
            {
                'firstname': 'Ægir',
                'middlename': '日本',
                'lastname': 'Müller-Łukasz',
            }
        )
        reparsed = vobject.readOne(partner._build_vcard().serialize())
        self.assertEqual(reparsed.n.value.family, 'Müller-Łukasz')
        self.assertEqual(reparsed.n.value.given, 'Ægir')
        self.assertEqual(reparsed.n.value.additional, '日本')
        self.assertEqual(reparsed.fn.value, 'Ægir 日本 Müller-Łukasz')

    def test_build_vcard_exports_the_extended_contact_details(self):
        partner = self.env['res.partner'].create(
            {
                'firstname': 'Detail',
                'lastname': 'Partner',
                'street': 'Main 1',
                'street2': 'Floor 3',
                'city': 'Vienna',
                'zip': '1010',
                'lang': 'en_US',
                'tz': 'Europe/Vienna',
                'gender': 'f',
                'birthdate': date(1990, 5, 1),
                'nickname': 'Dee',
                'role': 'Maintainer',
                'comment': '<p>Line one<br/>Line two</p>',
            }
        )
        serialized = partner._build_vcard().serialize()
        self.assertIn('LANG:en-US', serialized)
        self.assertIn('TZ:Europe/Vienna', serialized)
        self.assertIn('GENDER:F', serialized)
        self.assertIn('BDAY:19900501', serialized)
        self.assertIn('NICKNAME:Dee', serialized)
        self.assertIn('ROLE:Maintainer', serialized)
        self.assertIn('NOTE:', serialized)
        self.assertIn('Floor 3', serialized)

    def test_build_vcard_org_carries_the_department(self):
        company = self.env['res.partner'].create(
            {'name': 'Acme Inc', 'company_type': 'company'}
        )
        employee = self.env['res.partner'].create(
            {
                'firstname': 'Dep',
                'lastname': 'Member',
                'parent_id': company.id,
                'type': 'contact',
                'department': 'Research',
            }
        )
        self.assertIn('ORG:Acme Inc;Research', employee._build_vcard().serialize())

    def test_build_vcard_embeds_a_large_photo_without_corrupting_it(self):
        raw = _noise_png()
        partner = self.env['res.partner'].create(
            {
                'firstname': 'Photo',
                'lastname': 'Partner',
                'image_1920': base64.b64encode(raw),
            }
        )
        reparsed = vobject.readOne(partner._build_vcard().serialize())
        self.assertEqual(reparsed.photo.value, base64.b64decode(partner.avatar_512))
        self.assertGreater(len(reparsed.photo.value), 1024)

    def test_birthdate_derives_the_day_month_and_label(self):
        partner = self.env['res.partner'].create(
            {'name': 'Birthday Partner', 'birthdate': date(1990, 5, 1)}
        )
        self.assertEqual(partner.birthdate_day, 1)
        self.assertEqual(partner.birthdate_month, 5)
        self.assertTrue(partner.birthday)
        self.assertTrue(partner.birthdate_placeholder)
        partner.birthdate = False
        self.assertFalse(partner.birthdate_day)
        self.assertFalse(partner.birthdate_month)
        self.assertFalse(partner.birthday)
