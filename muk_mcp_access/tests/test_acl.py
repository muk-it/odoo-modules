from __future__ import annotations

from odoo.exceptions import AccessError
from odoo.tests import common, tagged
from odoo.tests.common import new_test_user


@tagged('post_install', '-at_install')
class TestMCPAccessACL(common.TransactionCase):
    """Cover the access rights guarding the MCP allowlist and its wizard."""

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
        cls.user = new_test_user(cls.env, login='mcp_access_acl_user')
        cls.entry = cls.access_model.create(
            {
                'model_id': cls.partner_model.id,
                'allow_read': True,
            }
        )

    # ----------------------------------------------------------
    # Tests
    # ----------------------------------------------------------

    def test_internal_user_cannot_create_allowlist_entries(self):
        with self.assertRaises(AccessError):
            self.access_model.with_user(self.user).create(
                {
                    'model_id': self.user_model.id,
                    'allow_read': True,
                }
            )

    def test_internal_user_cannot_write_allowlist_entries(self):
        with self.assertRaises(AccessError):
            self.entry.with_user(self.user).write({'allow_write': True})

    def test_internal_user_cannot_unlink_allowlist_entries(self):
        with self.assertRaises(AccessError):
            self.entry.with_user(self.user).unlink()

    def test_internal_user_can_read_the_whole_allowlist(self):
        rows = self.access_model.with_user(self.user).search_read(
            [],
            ['model_name', 'allow_read', 'allow_write', 'domain'],
        )
        self.assertEqual([row['model_name'] for row in rows], ['res.partner'])

    def test_internal_user_cannot_use_the_selection_wizard(self):
        with self.assertRaises(AccessError):
            self.wizard_model.with_user(self.user).create(
                {
                    'model_ids': [(6, 0, [self.user_model.id])],
                }
            )

    def test_internal_user_cannot_read_the_selection_wizard(self):
        wizard = self.wizard_model.create(
            {
                'model_ids': [(6, 0, [self.user_model.id])],
            }
        )
        with self.assertRaises(AccessError):
            wizard.with_user(self.user).read(['allow_read'])
