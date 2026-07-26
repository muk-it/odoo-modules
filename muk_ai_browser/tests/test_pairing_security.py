from __future__ import annotations

import json

from odoo import fields
from odoo.exceptions import AccessError
from odoo.tests import tagged
from odoo.tests.common import HttpCase, new_test_user


@tagged('post_install', '-at_install')
class TestPairingSecurity(HttpCase):
    """Verify a pairing code can only ever be minted for its own author."""

    # ----------------------------------------------------------
    # Setup
    # ----------------------------------------------------------

    def setUp(self) -> None:
        super().setUp()
        self.pairing = self.env['muk_mcp.pairing']
        self.key_model = self.env['muk_mcp.key']
        self.attacker = new_test_user(self.env, login='pairing_attacker')
        self.victim = self.env.ref('base.user_admin')

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    def _db_url(self, path: str) -> str:
        """Return a browser route URL with the current database selected."""
        return f'{path}?db={self.env.cr.dbname}'

    def _pair(self, code: str) -> dict:
        """POST ``code`` to the anonymous pair route and return its payload."""
        response = self.url_open(
            self._db_url('/muk_ai_browser/pair'),
            data=json.dumps({'pairing_code': code}).encode(),
            headers={'Content-Type': 'application/json'},
        )
        return response.json()

    # ----------------------------------------------------------
    # Tests
    # ----------------------------------------------------------

    def test_internal_user_cannot_forge_a_pairing_code(self):
        with self.assertRaises(AccessError):
            self.pairing.with_user(self.attacker).create(
                {
                    'code_hash': self.key_model._hash_key('chosen-by-attacker'),
                    'code_prefix': 'chosen-b',
                    'user_id': self.victim.id,
                    'scope': 'write',
                    'expires_at': fields.Datetime.add(
                        fields.Datetime.now(),
                        minutes=5,
                    ),
                },
            )

    def test_the_pair_route_mints_the_key_for_the_row_owner(self):
        forged = 'chosen-by-attacker'
        self.pairing.sudo().create(
            {
                'code_hash': self.key_model._hash_key(forged),
                'code_prefix': forged[:8],
                'user_id': self.victim.id,
                'scope': 'write',
                'expires_at': fields.Datetime.add(fields.Datetime.now(), minutes=5),
            },
        )
        result = self._pair(forged)
        self.assertEqual(
            self.key_model.authenticate(result['api_key']).user_id,
            self.victim,
            'the anonymous pair route trusts the row, so creating one must '
            'stay out of reach of an internal user',
        )

    def test_internal_user_cannot_read_pending_pairing_codes(self):
        self.pairing._mint_code(self.victim.id, 'Victim Laptop', 'write')
        with self.assertRaises(AccessError):
            self.pairing.with_user(self.attacker).search_read([], ['code_prefix'])

    def test_a_code_minted_for_a_user_pairs_only_that_user(self):
        code = self.pairing._mint_code(self.attacker.id, 'Own Laptop', 'read')
        result = self._pair(code)
        self.assertEqual(result['scope'], 'read')
        self.assertEqual(
            self.key_model.authenticate(result['api_key']).user_id,
            self.attacker,
        )

    def test_gc_drops_used_and_expired_codes_only(self):
        used = self.pairing._mint_code(self.victim.id, 'Used', 'write')
        expired = self.pairing._mint_code(self.victim.id, 'Expired', 'write')
        fresh = self.pairing._mint_code(self.victim.id, 'Fresh', 'write')
        self.pairing._consume(used)
        self.pairing.sudo().search(
            [('code_prefix', '=', expired[:8])]
        ).expires_at = fields.Datetime.subtract(fields.Datetime.now(), minutes=1)
        self.pairing._gc()
        remaining = self.pairing.sudo().search([]).mapped('code_prefix')
        self.assertNotIn(used[:8], remaining)
        self.assertNotIn(expired[:8], remaining)
        self.assertIn(fresh[:8], remaining)
