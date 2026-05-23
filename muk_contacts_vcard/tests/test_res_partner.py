import unittest
import vobject

from datetime import timedelta

from odoo import Command, fields
from odoo.tests.common import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestResPartner(TransactionCase):

    # ----------------------------------------------------------
    # Tests
    # ----------------------------------------------------------

    def test_name_is_computed_from_first_middle_last(self):
        partner = self.env['res.partner'].create({'name': 'Initial Name'})
        partner.write({
            'firstname': 'John',
            'middlename': 'M',
            'lastname': 'Doe',
        })
        self.assertEqual(partner.name, 'John M Doe')

    def test_name_inverse_splits_into_first_and_last(self):
        partner = self.env['res.partner'].create({
            'name': 'Initial Name'
        })
        partner.write({'name': 'Jane Smith'})
        self.assertEqual(partner.firstname, 'Jane')
        self.assertEqual(partner.lastname, 'Smith')
        self.assertFalse(partner.middlename)

    def test_formatted_name_can_include_honorific(self):
        prefix = self.env['muk_contacts_vcard.honorific'].create({
            'name': 'Dr.',
            'shortcut': 'Dr.',
            'position': 'preceding',
        })
        suffix = self.env['muk_contacts_vcard.honorific'].create({
            'name': 'PhD',
            'shortcut': 'PhD',
            'position': 'following',
        })
        partner = self.env['res.partner'].create({'name': 'Initial Name'})
        partner.write({
            'firstname': 'John',
            'lastname': 'Doe',
            'honorific_prefix_ids': [Command.set(prefix.ids)],
            'honorific_suffix_ids': [Command.set(suffix.ids)],
        })
        self.assertIn('Dr.', partner.formatted_name)
        self.assertIn('PhD', partner.formatted_name)

    def test_build_vcard_includes_uid_and_home_contacts(self):
        partner = self.env['res.partner'].create({'name': 'Initial Name'})
        partner.write({
            'firstname': 'John',
            'lastname': 'Doe',
            'email': 'john.doe@work.example.com',
            'email2': 'john.doe@home.example.com',
            'phone': '+431234',
            'phone2': '+439876',
            'gender': 'm',
            'birthdate': fields.Date.today() - timedelta(days=1),
            'nickname': 'Johnny',
        })
        self.assertTrue(partner.vcard_modified)
        serialized = partner._build_vcard().serialize()
        self.assertIn('UID:', serialized)
        self.assertIn(partner.vcard_uid, serialized)
        self.assertIn('EMAIL', serialized)
        self.assertIn('TYPE=HOME', serialized)

    def test_ensure_vcard_uid_sets_uid(self):
        partner = self.env['res.partner'].create({'name': 'Initial Name'})
        partner.write({
            'firstname': 'John',
            'lastname': 'Doe',
            'vcard_uid': False,
        })
        uid = partner._ensure_vcard_uid()
        self.assertTrue(uid)
        self.assertEqual(partner.vcard_uid, uid)

    def test_build_vcard_kind_org_for_company(self):
        company = self.env['res.partner'].create({
            'name': 'Acme Inc',
            'company_type': 'company',
        })
        self.assertIn('KIND:org', company._build_vcard().serialize())

    def test_build_vcard_kind_org_for_invoice_delivery_other(self):
        company = self.env['res.partner'].create({
            'name': 'Acme Inc',
            'company_type': 'company',
        })
        for ptype in ('invoice', 'delivery', 'other'):
            address = self.env['res.partner'].create({
                'name': f'{ptype.title()} Address',
                'parent_id': company.id,
                'type': ptype,
            })
            self.assertIn(
                'KIND:org',
                address._build_vcard().serialize(),
                msg=f'expected KIND:org for type={ptype}',
            )

    def test_build_vcard_kind_individual_for_contact(self):
        partner = self.env['res.partner'].create({
            'name': 'John Doe',
            'company_type': 'person',
            'type': 'contact',
        })
        self.assertIn('KIND:individual', partner._build_vcard().serialize())
