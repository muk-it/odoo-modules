from odoo.exceptions import UserError
from odoo.tests.common import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestResConfigSettings(TransactionCase):
    """Test the contact number automation toggle in the settings."""

    # ----------------------------------------------------------
    # Tests
    # ----------------------------------------------------------

    def test_the_toggle_mirrors_and_drives_the_sequence(self):
        sequence = self.env.ref('muk_contacts.sequence_contact_number')
        sequence.active = True
        settings = self.env['res.config.settings'].create({})
        self.assertTrue(settings.active_contact_number_automation)
        settings.write({'active_contact_number_automation': False})
        settings.set_values()
        self.assertFalse(sequence.active)
        self.assertFalse(
            self.env['res.config.settings'].create({}).active_contact_number_automation
        )
        settings.write({'active_contact_number_automation': True})
        settings.set_values()
        self.assertTrue(sequence.active)

    def test_disabling_the_automation_stops_numbering_new_partners(self):
        settings = self.env['res.config.settings'].create({})
        settings.write({'active_contact_number_automation': False})
        settings.set_values()
        partner = self.env['res.partner'].create({'name': 'Unnumbered Partner'})
        self.assertFalse(partner.contact_number)

    def test_saving_without_the_sequence_reports_a_user_error(self):
        self.env.ref('muk_contacts.sequence_contact_number').unlink()
        settings = self.env['res.config.settings'].create({})
        with self.assertRaises(UserError):
            settings.set_values()
