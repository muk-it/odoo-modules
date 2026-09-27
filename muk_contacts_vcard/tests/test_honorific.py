import vobject

from odoo import Command
from odoo.exceptions import AccessError
from odoo.tests import TransactionCase, new_test_user


class TestHonorific(TransactionCase):
    """Covers honorific abbreviations, ordering, search, and access rights."""

    # ----------------------------------------------------------
    # Tests
    # ----------------------------------------------------------

    def test_shortcut_defaults_to_the_title_and_keeps_an_explicit_one(self):
        model = self.env['muk_contacts_vcard.honorific']
        self.assertEqual(model.create({'name': 'Dr.'}).shortcut, 'Dr.')
        honorific = model.create({'name': 'Doctor', 'shortcut': 'Dr.'})
        honorific.write({'name': 'Doktor'})
        self.assertEqual(honorific.shortcut, 'Dr.')

    def test_formatted_name_and_vcard_follow_the_honorifics(self):
        model = self.env['muk_contacts_vcard.honorific']
        later = model.create({'name': 'Prof.', 'sequence': 20})
        earlier = model.create({'name': 'Doctor', 'shortcut': 'Dr.', 'sequence': 5})
        suffix = model.create({'name': 'PhD', 'position': 'following'})
        partner = self.env['res.partner'].create(
            {
                'firstname': 'Ordered',
                'lastname': 'Partner',
                'honorific_prefix_ids': [Command.set((later | earlier).ids)],
                'honorific_suffix_ids': [Command.set(suffix.ids)],
            }
        )
        self.assertEqual(partner.formatted_name, 'Dr. Prof. Ordered Partner PhD')
        self.env.flush_all()
        later.sequence = 1
        earlier.shortcut = 'Dr'
        self.assertIn(
            partner,
            self.env.records_to_compute(partner._fields['vcard_modified']),
        )
        self.assertEqual(partner.formatted_name, 'Prof. Dr Ordered Partner PhD')
        vcard = vobject.readOne(partner._build_vcard().serialize())
        self.assertEqual(vcard.fn.value, 'Prof. Dr Ordered Partner PhD')
        self.assertEqual(vcard.n.value.prefix, 'Prof. Dr')
        self.assertEqual(vcard.n.value.suffix, 'PhD')

    def test_a_title_is_found_by_its_abbreviation(self):
        title = self.env['muk_contacts_vcard.honorific'].create(
            {'name': 'Doctor of Laws', 'shortcut': 'LL.D.'}
        )
        found = self.env['muk_contacts_vcard.honorific'].name_search('LL.D')
        self.assertIn(title.id, [record_id for record_id, _label in found])

    def test_only_a_contact_manager_can_manage_honorifics(self):
        user = new_test_user(
            self.env, login='vcard_internal_honorific', groups='base.group_user'
        )
        with self.assertRaises(AccessError):
            self.env['muk_contacts_vcard.honorific'].with_user(user).create(
                {'name': 'Sir'}
            )
        manager = new_test_user(
            self.env,
            login='vcard_manager_honorific',
            groups='base.group_user,base.group_partner_manager',
        )
        honorific = (
            self.env['muk_contacts_vcard.honorific']
            .with_user(manager)
            .create({'name': 'Sir'})
        )
        honorific.write({'shortcut': 'Sr'})
        self.assertEqual(honorific.shortcut, 'Sr')
        honorific.unlink()
        self.assertFalse(honorific.exists())

    def test_a_portal_user_can_read_the_honorifics_of_a_partner(self):
        portal = new_test_user(
            self.env, login='vcard_portal', groups='base.group_portal'
        )
        honorific = self.env['muk_contacts_vcard.honorific'].create(
            {'name': 'Doctor', 'shortcut': 'Dr.'}
        )
        partner = portal.partner_id.commercial_partner_id
        partner.honorific_prefix_ids = [Command.set(honorific.ids)]
        result = partner.with_user(portal).mapped('honorific_prefix_ids.shortcut')
        self.assertEqual(result, ['Dr.'])
