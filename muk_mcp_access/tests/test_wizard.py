from odoo.tests import common


class TestModelSelectionWizard(common.TransactionCase):

    # ----------------------------------------------------------
    # Setup
    # ----------------------------------------------------------

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.access_model = cls.env['muk_mcp_access.model']
        cls.wizard_model = cls.env['muk_mcp_access.model.selection']
        cls.partner_model = cls.env.ref('base.model_res_partner')
        cls.user_model = cls.env.ref('base.model_res_users')

    # ----------------------------------------------------------
    # Tests
    # ----------------------------------------------------------

    def test_wizard_creates_entries(self):
        wizard = self.wizard_model.create({
            'model_ids': [(6, 0, [
                self.partner_model.id,
                self.user_model.id,
            ])],
            'allow_read': True,
            'allow_write': False,
        })
        wizard.action_enable_models()
        entries = self.access_model.search([])
        self.assertEqual(len(entries), 2)
        partner_entry = entries.filtered(
            lambda e: e.model_name == 'res.partner'
        )
        self.assertTrue(partner_entry.allow_read)
        self.assertFalse(partner_entry.allow_write)

    def test_wizard_skips_duplicates(self):
        self.access_model.create({
            'model_id': self.partner_model.id,
        })
        wizard = self.wizard_model.create({
            'model_ids': [(6, 0, [
                self.partner_model.id,
                self.user_model.id,
            ])],
            'allow_read': True,
            'allow_write': True,
        })
        wizard.action_enable_models()
        entries = self.access_model.search([])
        self.assertEqual(len(entries), 2)
        partner_entry = entries.filtered(
            lambda e: e.model_name == 'res.partner'
        )
        self.assertTrue(partner_entry.allow_read)
        self.assertFalse(partner_entry.allow_write)

    def test_wizard_applies_write_permission(self):
        wizard = self.wizard_model.create({
            'model_ids': [(6, 0, [self.partner_model.id])],
            'allow_read': True,
            'allow_write': True,
        })
        wizard.action_enable_models()
        entry = self.access_model.search([
            ('model_name', '=', 'res.partner'),
        ])
        self.assertTrue(entry.allow_write)
