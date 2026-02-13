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

    @unittest.skipIf(vobject is None, 'vobject python package is not available')
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
