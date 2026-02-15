from odoo.tests.common import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestResPartner(TransactionCase):

    # ----------------------------------------------------------
    # Tests
    # ----------------------------------------------------------

    def test_contact_number_is_generated_on_action(self):
        partner = self.env['res.partner'].create({
            'contact_number': False,
            'name': 'Test Partner',
        })
        partner.action_generate_contact_number()
        self.assertTrue(partner.contact_number)
