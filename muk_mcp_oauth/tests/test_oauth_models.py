# Copyright 2026, Jarsa
# License LGPL-3.0 or later (http://www.gnu.org/licenses/lgpl.html).

import base64
import hashlib
from datetime import timedelta

from odoo import fields
from odoo.tests.common import TransactionCase

CALLBACK = "https://claude.ai/api/mcp/auth_callback"


def make_pkce(verifier):
    digest = hashlib.sha256(verifier.encode()).digest()
    return base64.urlsafe_b64encode(digest).decode().rstrip("=")


class TestOAuthModels(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.client = cls.env["muk_mcp.oauth.client"].create(
            {
                "client_name": "Claude",
                "redirect_uris": f"{CALLBACK}\nhttp://localhost/callback",
            }
        )
        cls.user = cls.env["res.users"].create({"name": "OAuth Test User", "login": "oauth_test_user"})

    def _issue_code(self, verifier="a-test-code-verifier-of-decent-length-12345", **overrides):
        values = {
            "client": self.client,
            "user": self.user,
            "scope": "mcp:read mcp:write",
            "code_challenge": make_pkce(verifier),
            "redirect_uri": CALLBACK,
        }
        values.update(overrides)
        raw_code = self.env["muk_mcp.oauth.code"]._issue(
            values["client"],
            values["user"],
            values["scope"],
            values["code_challenge"],
            values["redirect_uri"],
        )
        return raw_code, verifier

    def test_uri_whitelist(self):
        allowed = self.env["muk_mcp.oauth.client"]._is_uri_allowed
        self.assertTrue(allowed(CALLBACK))
        self.assertTrue(allowed("https://claude.com/api/mcp/auth_callback"))
        self.assertTrue(allowed("http://localhost:53211/callback"))
        self.assertTrue(allowed("http://127.0.0.1:8123/callback"))
        self.assertFalse(allowed("http://claude.ai/api/mcp/auth_callback"))
        self.assertFalse(allowed("https://evil.com/callback"))
        self.assertFalse(allowed("https://claude.ai.evil.com/callback"))
        self.assertFalse(allowed("http://192.168.1.10/callback"))
        self.assertFalse(allowed(""))

    def test_match_redirect_uri(self):
        self.assertTrue(self.client._match_redirect_uri(CALLBACK))
        self.assertFalse(self.client._match_redirect_uri("https://claude.ai/other/path"))
        # Loopback matching ignores the port only (RFC 8252).
        self.assertTrue(self.client._match_redirect_uri("http://localhost:60123/callback"))
        self.assertFalse(self.client._match_redirect_uri("http://localhost:60123/other"))
        self.assertFalse(self.client._match_redirect_uri("http://127.0.0.1:60123/callback"))

    def test_code_happy_path(self):
        raw_code, verifier = self._issue_code()
        code = self.env["muk_mcp.oauth.code"]._consume(raw_code, self.client, CALLBACK, verifier)
        self.assertTrue(code)
        self.assertEqual(code.user_id, self.user)
        self.assertTrue(code.used)

    def test_code_single_use(self):
        raw_code, verifier = self._issue_code()
        code_model = self.env["muk_mcp.oauth.code"]
        self.assertTrue(code_model._consume(raw_code, self.client, CALLBACK, verifier))
        self.assertFalse(code_model._consume(raw_code, self.client, CALLBACK, verifier))

    def test_code_wrong_verifier(self):
        raw_code, __ = self._issue_code()
        code = self.env["muk_mcp.oauth.code"]._consume(
            raw_code, self.client, CALLBACK, "not-the-right-verifier-but-long-enough"
        )
        self.assertFalse(code)

    def test_code_expired(self):
        raw_code, verifier = self._issue_code()
        record = self.env["muk_mcp.oauth.code"].search(
            [("code_hash", "=", self.env["muk_mcp.key"]._hash_key(raw_code))], limit=1
        )
        record.sudo().write({"expiration": fields.Datetime.now() - timedelta(seconds=1)})
        self.assertFalse(self.env["muk_mcp.oauth.code"]._consume(raw_code, self.client, CALLBACK, verifier))

    def test_code_redirect_uri_mismatch(self):
        raw_code, verifier = self._issue_code()
        code = self.env["muk_mcp.oauth.code"]._consume(raw_code, self.client, "https://claude.ai/other", verifier)
        self.assertFalse(code)

    def test_token_issue_materializes_key(self):
        token, access_raw, refresh_raw = self.env["muk_mcp.oauth.token"]._issue(
            self.client, self.user, "mcp:read mcp:write"
        )
        self.assertTrue(token.mcp_key_id)
        self.assertEqual(token.mcp_key_id.user_id, self.user)
        self.assertEqual(token.mcp_key_id.scope, "write")
        self.assertNotEqual(access_raw, refresh_raw)
        # Only hashes are stored.
        self.assertNotIn(access_raw, (token.access_token_hash, token.refresh_token_hash))
        key_model = self.env["muk_mcp.key"]
        self.assertEqual(token.access_token_hash, key_model._hash_key(access_raw))
        self.assertEqual(token.refresh_token_hash, key_model._hash_key(refresh_raw))

    def test_token_scope_read_only(self):
        token, __, __ = self.env["muk_mcp.oauth.token"]._issue(self.client, self.user, "mcp:read")
        self.assertEqual(token.mcp_key_id.scope, "read")

    def test_authenticate_oauth_token(self):
        token, access_raw, __ = self.env["muk_mcp.oauth.token"]._issue(self.client, self.user, "mcp:read mcp:write")
        key = self.env["muk_mcp.key"].authenticate(access_raw)
        self.assertEqual(key, token.mcp_key_id)
        self.assertEqual(key.user_id, self.user)
        self.assertTrue(token.last_used)

    def test_authenticate_expired_access_token(self):
        token, access_raw, __ = self.env["muk_mcp.oauth.token"]._issue(self.client, self.user, "mcp:read")
        token.sudo().write({"access_expiration": fields.Datetime.now() - timedelta(seconds=1)})
        self.assertFalse(self.env["muk_mcp.key"].authenticate(access_raw))

    def test_authenticate_revoked_token(self):
        token, access_raw, __ = self.env["muk_mcp.oauth.token"]._issue(self.client, self.user, "mcp:read")
        token.action_revoke()
        self.assertFalse(self.env["muk_mcp.key"].authenticate(access_raw))
        self.assertFalse(token.mcp_key_id.active)

    def test_authenticate_regular_key_untouched(self):
        data = self.env["muk_mcp.key"].generate_playground_key(name="Plain", scope="write")
        key = self.env["muk_mcp.key"].authenticate(data["plaintext"])
        self.assertEqual(key.id, data["id"])

    def test_token_unlink_removes_key(self):
        token, __, __ = self.env["muk_mcp.oauth.token"]._issue(self.client, self.user, "mcp:read")
        key = token.mcp_key_id
        token.unlink()
        self.assertFalse(key.exists())
