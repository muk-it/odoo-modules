from __future__ import annotations

import secrets
from typing import Any

from odoo import models
from odoo.exceptions import AccessError
from odoo.tests import common, tagged
from odoo.tests.common import new_test_user
from odoo.tools import SQL


@tagged('post_install', '-at_install')
class TestMcpKeyLifecycle(common.TransactionCase):
    """Cover key minting through the wizard, secret storage and session revocation."""

    # ----------------------------------------------------------
    # Setup
    # ----------------------------------------------------------

    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls.key_model = cls.env['muk_mcp.key']
        cls.session_model = cls.env['muk_mcp.session']
        cls.config = cls.env['ir.config_parameter'].sudo()

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    def _make_key(
        self,
        user: models.BaseModel,
        rate_limit: int = 60,
    ) -> tuple[str, models.BaseModel]:
        """Create a key owned by ``user`` and return its plaintext and record."""
        raw_key = secrets.token_urlsafe(32)
        record = self.key_model.create(
            {
                'name': 'Lifecycle Key',
                'user_id': user.id,
                'key_hash': self.key_model._hash_key(raw_key),
                'key_prefix': raw_key[:8],
                'rate_limit': rate_limit,
            },
        )
        return raw_key, record

    def _read_key_row(self, key_id: int) -> dict[str, Any]:
        """Return the raw database row backing a key, bypassing the ORM cache."""
        self.env.flush_all()
        self.env.cr.execute(
            SQL(
                'SELECT * FROM %s WHERE id = %s',
                SQL.identifier(self.key_model._table),
                key_id,
            ),
        )
        return self.env.cr.dictfetchone()

    # ----------------------------------------------------------
    # Tests: generate-key wizard
    # ----------------------------------------------------------

    def test_wizard_mints_a_working_key_and_reveals_it_once(self):
        owner = new_test_user(
            self.env,
            login='mcp_wizard_owner',
            groups='base.group_user',
        )
        wizard = (
            self.env['muk_mcp.generate_key']
            .with_user(owner)
            .create(
                {
                    'name': 'Wizard Key',
                    'scope': 'read',
                    'rate_limit': 12,
                },
            )
        )
        before = self.key_model.search([])
        action = wizard.action_make_key()
        self.assertFalse(wizard.exists())
        self.assertEqual(action['res_model'], 'muk_mcp.key.show')
        raw_key = action['context']['default_key']
        key = self.key_model.search([]) - before
        self.assertEqual(len(key), 1)
        self.assertEqual(key.name, 'Wizard Key')
        self.assertEqual(key.user_id, owner)
        self.assertEqual(key.scope, 'read')
        self.assertEqual(key.rate_limit, 12)
        self.assertEqual(key.key_prefix, raw_key[:8])
        self.assertEqual(key.key_hash, self.key_model._hash_key(raw_key))
        self.assertEqual(self.key_model.authenticate(raw_key), key)

    def test_wizard_rate_limit_defaults_to_the_configured_value(self):
        self.config.set_param('muk_mcp.rate_limit_requests', '17')
        wizard = self.env['muk_mcp.generate_key'].create({'name': 'Default Limit'})
        self.assertEqual(wizard.rate_limit, 17)

    # ----------------------------------------------------------
    # Tests: playground key generation
    # ----------------------------------------------------------

    def test_generate_playground_key_uses_the_configured_rate_limit(self):
        self.config.set_param('muk_mcp.rate_limit_requests', '7')
        result = self.key_model.generate_playground_key(name='Configured')
        self.assertEqual(result['rate_limit'], 7)
        self.assertEqual(self.key_model.browse(result['id']).rate_limit, 7)

    # ----------------------------------------------------------
    # Tests: secret storage
    # ----------------------------------------------------------

    def test_plaintext_key_is_never_stored(self):
        result = self.key_model.generate_playground_key(name='Secret')
        raw_key = result['plaintext']
        row = self._read_key_row(result['id'])
        self.assertEqual(row['key_hash'], self.key_model._hash_key(raw_key))
        self.assertEqual(row['key_prefix'], raw_key[:8])
        self.assertNotIn(raw_key, [str(value) for value in row.values()])

    # ----------------------------------------------------------
    # Tests: ownership boundaries
    # ----------------------------------------------------------

    def test_user_can_raise_the_rate_limit_of_their_own_key(self):
        user = new_test_user(
            self.env,
            login='mcp_selfraise',
            groups='base.group_user',
        )
        _raw_key, key = self._make_key(user, rate_limit=5)
        key.with_user(user).write({'rate_limit': 999999})
        self.assertEqual(key.rate_limit, 999999)

    def test_user_cannot_write_another_users_key(self):
        owner = new_test_user(self.env, login='mcp_owner', groups='base.group_user')
        other = new_test_user(self.env, login='mcp_other', groups='base.group_user')
        _raw_key, key = self._make_key(owner, rate_limit=5)
        with self.assertRaises(AccessError):
            key.with_user(other).write({'rate_limit': 999999})
        self.assertEqual(key.rate_limit, 5)

    # ----------------------------------------------------------
    # Tests: session revocation
    # ----------------------------------------------------------

    def test_action_revoke_mcp_sessions_deactivates_only_that_users_sessions(self):
        owner = new_test_user(self.env, login='mcp_revoke', groups='base.group_user')
        other = new_test_user(self.env, login='mcp_keep', groups='base.group_user')
        mine = self.session_model.create(
            [
                {'user_id': owner.id},
                {'user_id': owner.id},
            ],
        )
        theirs = self.session_model.create({'user_id': other.id})
        action = owner.action_revoke_mcp_sessions()
        self.assertEqual(action['tag'], 'reload')
        self.assertEqual(mine.mapped('active'), [False, False])
        self.assertTrue(theirs.active)
