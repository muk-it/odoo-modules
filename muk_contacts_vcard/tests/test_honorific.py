from odoo import Command
from odoo.exceptions import AccessError
from odoo.tests.common import TransactionCase, new_test_user, tagged


@tagged('post_install', '-at_install')
class TestHonorific(TransactionCase):
    """Covers honorific abbreviations, ordering, and access rights."""

    # ----------------------------------------------------------
    # Tests
    # ----------------------------------------------------------

    def test_shortcut_is_computed_from_name_when_missing(self):
        honorific = self.env['muk_contacts_vcard.honorific'].create(
            {
                'name': 'Dr.',
                'position': 'preceding',
            }
        )
        self.assertEqual(honorific.shortcut, 'Dr.')

    def test_shortcut_keeps_an_explicit_abbreviation_when_the_title_changes(self):
        honorific = self.env['muk_contacts_vcard.honorific'].create(
            {
                'name': 'Doctor',
                'shortcut': 'Dr.',
                'position': 'preceding',
            }
        )
        honorific.write({'name': 'Doktor'})
        self.assertEqual(honorific.shortcut, 'Dr.')

    def test_formatted_name_orders_the_honorifics_by_sequence(self):
        model = self.env['muk_contacts_vcard.honorific']
        later = model.create({'name': 'Prof.', 'position': 'preceding', 'sequence': 20})
        earlier = model.create({'name': 'Dr.', 'position': 'preceding', 'sequence': 5})
        partner = self.env['res.partner'].create(
            {
                'firstname': 'Ordered',
                'lastname': 'Partner',
                'honorific_prefix_ids': [Command.set((later | earlier).ids)],
            }
        )
        self.assertEqual(partner.formatted_name, 'Dr. Prof. Ordered Partner')

    def test_an_internal_user_cannot_create_a_honorific(self):
        user = new_test_user(
            self.env, login='vcard_internal_honorific', groups='base.group_user'
        )
        with self.assertRaises(AccessError):
            self.env['muk_contacts_vcard.honorific'].with_user(user).create(
                {'name': 'Sir', 'position': 'preceding'}
            )

    def test_a_contact_manager_can_manage_honorifics(self):
        user = new_test_user(
            self.env,
            login='vcard_manager_honorific',
            groups='base.group_user,base.group_partner_manager',
        )
        model = self.env['muk_contacts_vcard.honorific'].with_user(user)
        honorific = model.create({'name': 'Sir', 'position': 'preceding'})
        honorific.write({'shortcut': 'Sr'})
        self.assertEqual(honorific.shortcut, 'Sr')
        honorific.unlink()
        self.assertFalse(honorific.exists())
