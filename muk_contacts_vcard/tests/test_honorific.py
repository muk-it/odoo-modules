from odoo.tests.common import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestHonorific(TransactionCase):

    # ----------------------------------------------------------
    # Tests
    # ----------------------------------------------------------

    def test_shortcut_is_computed_from_name_when_missing(self):
        honorific = self.env['muk_contacts_vcard.honorific'].create({
            'name': 'Dr.',
            'position': 'preceding',
        })
        self.assertEqual(honorific.shortcut, 'Dr.')
