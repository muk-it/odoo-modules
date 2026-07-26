from __future__ import annotations

from psycopg2 import IntegrityError

from odoo.tests import common, tagged
from odoo.tools import mute_logger
from odoo.tools.safe_eval import safe_eval


@tagged('post_install', '-at_install')
class TestModelSelectionWizard(common.TransactionCase):
    """Test the MCP model selection wizard."""

    # ----------------------------------------------------------
    # Setup
    # ----------------------------------------------------------

    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls.access_model = cls.env['muk_mcp_access.model']
        cls.wizard_model = cls.env['muk_mcp_access.model.selection']
        cls.partner_model = cls.env.ref('base.model_res_partner')
        cls.user_model = cls.env.ref('base.model_res_users')

    # ----------------------------------------------------------
    # Tests
    # ----------------------------------------------------------

    def test_wizard_creates_entries(self):
        wizard = self.wizard_model.create(
            {
                'model_ids': [
                    (
                        6,
                        0,
                        [
                            self.partner_model.id,
                            self.user_model.id,
                        ],
                    )
                ],
                'allow_read': True,
                'allow_write': False,
            }
        )
        wizard.action_enable_models()
        entries = self.access_model.search([])
        self.assertEqual(len(entries), 2)
        partner_entry = entries.filtered(lambda e: e.model_name == 'res.partner')
        self.assertTrue(partner_entry.allow_read)
        self.assertFalse(partner_entry.allow_write)

    def test_wizard_skips_duplicates(self):
        self.access_model.create(
            {
                'model_id': self.partner_model.id,
            }
        )
        wizard = self.wizard_model.create(
            {
                'model_ids': [
                    (
                        6,
                        0,
                        [
                            self.partner_model.id,
                            self.user_model.id,
                        ],
                    )
                ],
                'allow_read': True,
                'allow_write': True,
            }
        )
        wizard.action_enable_models()
        entries = self.access_model.search([])
        self.assertEqual(len(entries), 2)
        partner_entry = entries.filtered(lambda e: e.model_name == 'res.partner')
        self.assertTrue(partner_entry.allow_read)
        self.assertFalse(partner_entry.allow_write)

    def test_wizard_returns_close_action(self):
        wizard = self.wizard_model.create(
            {
                'model_ids': [(6, 0, [self.partner_model.id])],
            }
        )
        self.assertEqual(
            wizard.action_enable_models(),
            {'type': 'ir.actions.act_window_close'},
        )

    def test_model_ids_domain_excludes_listed_and_transient_models(self):
        self.access_model.create(
            {
                'model_id': self.partner_model.id,
            }
        )
        wizard = self.wizard_model.create(
            {
                'model_ids': [(6, 0, [self.user_model.id])],
            }
        )
        self.assertIn(self.partner_model, wizard._existing_model_ids)
        self.assertNotIn(self.user_model, wizard._existing_model_ids)
        domain = safe_eval(
            self.wizard_model._fields['model_ids'].domain,
            {'_existing_model_ids': wizard._existing_model_ids.ids},
        )
        selectable = self.env['ir.model'].search(domain)
        self.assertNotIn(self.partner_model, selectable)
        self.assertIn(self.user_model, selectable)
        wizard_model_entry = self.env['ir.model'].search(
            [('model', '=', 'muk_mcp_access.model.selection')],
        )
        self.assertTrue(wizard_model_entry)
        self.assertNotIn(wizard_model_entry, selectable)

    def test_wizard_archived_entry_collision_raises_integrity_error(self):
        entry = self.access_model.create(
            {
                'model_id': self.partner_model.id,
            }
        )
        entry.active = False
        wizard = self.wizard_model.create(
            {
                'model_ids': [(6, 0, [self.partner_model.id])],
            }
        )
        with (
            mute_logger('odoo.sql_db'),
            self.assertRaises(IntegrityError),
            self.cr.savepoint(),
        ):
            wizard.action_enable_models()

    def test_wizard_multi_record_raises_singleton_error(self):
        wizards = self.wizard_model.create(
            [
                {'model_ids': [(6, 0, [self.partner_model.id])]},
                {'model_ids': [(6, 0, [self.user_model.id])]},
            ]
        )
        self.assertEqual(len(wizards), 2)
        with self.assertRaises(ValueError):
            wizards.action_enable_models()
        self.assertFalse(self.access_model.search([]))
