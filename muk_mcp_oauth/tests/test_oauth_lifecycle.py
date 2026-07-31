# Copyright 2026, Jarsa
# License LGPL-3.0 or later (http://www.gnu.org/licenses/lgpl.html).

from datetime import timedelta

from odoo import fields
from odoo.exceptions import AccessError
from odoo.tests.common import TransactionCase


class TestOAuthLifecycle(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.client = cls.env["muk_mcp.oauth.client"].create(
            {
                "client_name": "Claude",
                "redirect_uris": "https://claude.ai/api/mcp/auth_callback",
            }
        )
        cls.user = cls.env["res.users"].create({"name": "OAuth Lifecycle User", "login": "oauth_lifecycle_user"})

    def _issue(self, scope="mcp:read mcp:write"):
        return self.env["muk_mcp.oauth.token"]._issue(self.client, self.user, scope)

    def test_refresh_rotation(self):
        token, access_raw, refresh_raw = self._issue()
        key = token.mcp_key_id
        rotated, new_access, new_refresh = self.env["muk_mcp.oauth.token"]._refresh(refresh_raw, self.client)
        self.assertEqual(rotated, token)
        # Same key record (audit log continuity), new hash.
        self.assertEqual(rotated.mcp_key_id, key)
        self.assertNotEqual(new_access, access_raw)
        key_model = self.env["muk_mcp.key"]
        self.assertEqual(key.key_hash, key_model._hash_key(new_access))
        # Old credentials are dead, new ones work.
        self.assertFalse(key_model.authenticate(access_raw))
        self.assertEqual(key_model.authenticate(new_access), key)
        old_retry = self.env["muk_mcp.oauth.token"]._refresh(refresh_raw, self.client)
        self.assertFalse(old_retry[0])
        # The new refresh token still rotates.
        again = self.env["muk_mcp.oauth.token"]._refresh(new_refresh, self.client)
        self.assertEqual(again[0], token)

    def test_refresh_expired(self):
        token, __, refresh_raw = self._issue()
        token.write({"refresh_expiration": fields.Datetime.now() - timedelta(seconds=1)})
        self.assertFalse(self.env["muk_mcp.oauth.token"]._refresh(refresh_raw, self.client)[0])

    def test_refresh_revoked(self):
        token, __, refresh_raw = self._issue()
        token.action_revoke()
        self.assertFalse(self.env["muk_mcp.oauth.token"]._refresh(refresh_raw, self.client)[0])

    def test_refresh_absolute_cap(self):
        token, __, refresh_raw = self._issue()
        cap = fields.Datetime.now() + timedelta(days=3)
        token.write({"absolute_expiration": cap})
        rotated, __, new_refresh = self.env["muk_mcp.oauth.token"]._refresh(refresh_raw, self.client)
        self.assertEqual(rotated.refresh_expiration, cap)
        # Past the cap the chain is over even with a valid refresh token.
        token.write({"absolute_expiration": fields.Datetime.now() - timedelta(seconds=1)})
        self.assertFalse(self.env["muk_mcp.oauth.token"]._refresh(new_refresh, self.client)[0])

    def test_revoke_value(self):
        token, access_raw, __ = self._issue()
        self.env["muk_mcp.oauth.token"]._revoke_value(access_raw)
        self.assertTrue(token.revoked)
        self.assertFalse(token.mcp_key_id.active)
        token2, __, refresh_raw2 = self._issue()
        self.env["muk_mcp.oauth.token"]._revoke_value(refresh_raw2)
        self.assertTrue(token2.revoked)

    def test_action_revoke_own_only(self):
        token, __, __ = self._issue()
        stranger = self.env["res.users"].create({"name": "Stranger", "login": "oauth_stranger_user"})
        with self.assertRaises(AccessError):
            token.with_user(stranger).action_revoke()
        token.with_user(self.user).action_revoke()
        self.assertTrue(token.revoked)

    def test_gc_codes(self):
        code_model = self.env["muk_mcp.oauth.code"]
        raw_code = code_model._issue(self.client, self.user, "mcp:read", "challenge", "https://claude.ai/cb")
        expired = code_model.search([("code_hash", "=", self.env["muk_mcp.key"]._hash_key(raw_code))])
        expired.write({"expiration": fields.Datetime.now() - timedelta(seconds=1)})
        code_model._gc_codes()
        self.assertFalse(expired.exists())

    def test_gc_tokens(self):
        token, __, __ = self._issue()
        key = token.mcp_key_id
        token.write({"refresh_expiration": fields.Datetime.now() - timedelta(seconds=1)})
        self.env["muk_mcp.oauth.token"]._gc_tokens()
        self.assertFalse(token.exists())
        self.assertFalse(key.exists())

    def test_gc_clients(self):
        old_date = fields.Datetime.now() - timedelta(days=90)
        idle, live = self.env["muk_mcp.oauth.client"].create(
            [
                {"client_name": "Idle", "redirect_uris": "http://localhost/callback"},
                {"client_name": "Live", "redirect_uris": "http://localhost/callback"},
            ]
        )
        self.env.cr.execute(
            "UPDATE muk_mcp_oauth_client SET create_date = %s WHERE id IN %s",
            (old_date, tuple((idle | live).ids)),
        )
        (idle | live).invalidate_recordset()
        self.env["muk_mcp.oauth.token"]._issue(live, self.user, "mcp:read")
        self.env["muk_mcp.oauth.client"]._gc_clients()
        self.assertFalse(idle.active)
        self.assertTrue(live.active)
