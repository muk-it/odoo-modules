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

    def test_build_vcard_drops_org_for_company(self):
        company = self.env['res.partner'].create({
            'name': 'Acme Inc',
            'company_type': 'company',
        })
        serialized = company._build_vcard().serialize()
        self.assertNotIn('ORG:', serialized)
        self.assertNotIn('ORG;', serialized)

    def test_build_vcard_keeps_org_for_individual(self):
        company = self.env['res.partner'].create({
            'name': 'Acme Inc',
            'company_type': 'company',
        })
        employee = self.env['res.partner'].create({
            'name': 'Jane Doe',
            'parent_id': company.id,
            'type': 'contact',
        })
        self.assertIn('ORG:Acme Inc', employee._build_vcard().serialize())

    def test_build_vcard_kind_org_for_company(self):
        company = self.env['res.partner'].create({
            'name': 'Acme Inc',
            'company_type': 'company',
        })
        self.assertIn('KIND:org', company._build_vcard().serialize())

    def test_build_vcard_kind_individual_for_contact(self):
        partner = self.env['res.partner'].create({
            'name': 'John Doe',
            'company_type': 'person',
            'type': 'contact',
        })
        self.assertIn('KIND:individual', partner._build_vcard().serialize())

    def test_build_vcard_company_embeds_child_addresses_as_labeled_adr(self):
        company = self.env['res.partner'].create({
            'name': 'Acme Inc',
            'company_type': 'company',
            'street': '1 Main St',
            'city': 'HQ City',
        })
        self.env['res.partner'].create({
            'name': 'Invoice Address',
            'parent_id': company.id,
            'type': 'invoice',
            'street': '10 Billing Rd',
            'city': 'Bill City',
            'zip': '12345',
        })
        self.env['res.partner'].create({
            'name': 'Delivery Address',
            'parent_id': company.id,
            'type': 'delivery',
            'street': '20 Ship Ave',
            'city': 'Ship City',
        })
        self.env['res.partner'].create({
            'name': 'Other Address',
            'parent_id': company.id,
            'type': 'other',
            'street': '30 Side St',
        })
        self.env['res.partner'].create({
            'name': 'Jane Doe',
            'parent_id': company.id,
            'type': 'contact',
        })
        serialized = company._build_vcard().serialize()
        import re
        groups = dict(
            re.findall(r'(item\d+)\.X-ABLABEL:([^\r\n]+)', serialized)
        )
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
        company = self.env['res.partner'].create({
            'name': 'Acme Inc',
            'company_type': 'company',
        })
        self.env['res.partner'].create({
            'name': 'Vienna Office Billing',
            'parent_id': company.id,
            'type': 'invoice',
            'street': '10 Billing Rd',
        })
        self.env['res.partner'].create({
            'name': 'Acme Inc',
            'parent_id': company.id,
            'type': 'delivery',
            'street': '20 Ship Ave',
        })
        serialized = company._build_vcard().serialize()
        self.assertIn('X-ABLABEL:Vienna Office Billing', serialized)
        self.assertNotIn('X-ABLABEL:Acme Inc', serialized)
        import re
        self.assertEqual(
            len(re.findall(r'X-ABLABEL:', serialized)),
            2,
            msg='expected 2 labels (custom + delivery fallback)',
        )

    def test_build_vcard_company_skips_empty_child_addresses(self):
        company = self.env['res.partner'].create({
            'name': 'Acme Inc',
            'company_type': 'company',
        })
        self.env['res.partner'].create({
            'name': 'Empty Invoice',
            'parent_id': company.id,
            'type': 'invoice',
        })
        serialized = company._build_vcard().serialize()
        self.assertNotIn('X-ABLABEL', serialized)

    def test_build_vcard_individual_does_not_embed_child_addresses(self):
        company = self.env['res.partner'].create({
            'name': 'Acme Inc',
            'company_type': 'company',
        })
        person = self.env['res.partner'].create({
            'name': 'John Doe',
            'company_type': 'person',
            'type': 'contact',
            'parent_id': company.id,
        })
        self.env['res.partner'].create({
            'name': 'Invoice Address',
            'parent_id': company.id,
            'type': 'invoice',
            'street': '10 Billing Rd',
        })
        serialized = person._build_vcard().serialize()
        self.assertNotIn('X-ABLABEL', serialized)
