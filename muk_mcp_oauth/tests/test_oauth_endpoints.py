# Copyright 2026, Jarsa
# License LGPL-3.0 or later (http://www.gnu.org/licenses/lgpl.html).

import base64
import hashlib
import json
import re
from urllib.parse import parse_qs, urlencode, urlparse

from odoo.tests.common import HttpCase, tagged

CALLBACK = "https://claude.ai/api/mcp/auth_callback"
VERIFIER = "an-oauth-test-code-verifier-with-plenty-of-length"


def make_pkce(verifier):
    digest = hashlib.sha256(verifier.encode()).digest()
    return base64.urlsafe_b64encode(digest).decode().rstrip("=")


@tagged("post_install", "-at_install")
class TestOAuthEndpoints(HttpCase):
    def _register(self, redirect_uris=None):
        response = self.url_open(
            "/oauth2/register",
            data=json.dumps(
                {
                    "client_name": "Claude",
                    "redirect_uris": redirect_uris or [CALLBACK],
                }
            ),
            headers={"Content-Type": "application/json"},
        )
        return response

    def _authorize_params(self, client_id, **overrides):
        params = {
            "response_type": "code",
            "client_id": client_id,
            "redirect_uri": CALLBACK,
            "state": "test-state",
            "scope": "mcp:read mcp:write",
            "code_challenge": make_pkce(VERIFIER),
            "code_challenge_method": "S256",
        }
        params.update(overrides)
        return params

    def _authorize(self, client_id, decision="accept", **overrides):
        """Run the consent screen as admin and return the redirect Location."""
        self.authenticate("admin", "admin")
        params = self._authorize_params(client_id, **overrides)
        page = self.url_open(f"/oauth2/authorize?{urlencode(params)}")
        self.assertEqual(page.status_code, 200)
        self.assertIn("Claude", page.text)
        csrf_token = re.search(r'name="csrf_token" value="([^"]+)"', page.text).group(1)
        response = self.url_open(
            "/oauth2/authorize",
            data={**params, "csrf_token": csrf_token, "decision": decision},
            allow_redirects=False,
        )
        self.assertIn(response.status_code, (302, 303))
        return response.headers["Location"]

    def _exchange(self, client_id, code, verifier=VERIFIER, redirect_uri=CALLBACK):
        return self.url_open(
            "/oauth2/token",
            data={
                "grant_type": "authorization_code",
                "code": code,
                "client_id": client_id,
                "redirect_uri": redirect_uri,
                "code_verifier": verifier,
            },
        )

    def _mcp_initialize(self, access_token):
        return self.url_open(
            "/mcp",
            data=json.dumps(
                {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "initialize",
                    "params": {
                        "protocolVersion": "2025-03-26",
                        "capabilities": {},
                        "clientInfo": {"name": "test", "version": "1.0"},
                    },
                }
            ),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {access_token}",
            },
        )

    def test_well_known_documents(self):
        for path in (
            "/.well-known/oauth-protected-resource",
            "/.well-known/oauth-protected-resource/mcp",
        ):
            response = self.url_open(path)
            self.assertEqual(response.status_code, 200)
            document = response.json()
            self.assertTrue(document["resource"].endswith("/mcp"))
            self.assertEqual(document["scopes_supported"], ["mcp:read", "mcp:write"])
            self.assertEqual(response.headers.get("Access-Control-Allow-Origin"), "*")
        response = self.url_open("/.well-known/oauth-authorization-server")
        self.assertEqual(response.status_code, 200)
        document = response.json()
        self.assertTrue(document["authorization_endpoint"].endswith("/oauth2/authorize"))
        self.assertTrue(document["token_endpoint"].endswith("/oauth2/token"))
        self.assertTrue(document["registration_endpoint"].endswith("/oauth2/register"))
        self.assertEqual(document["code_challenge_methods_supported"], ["S256"])
        self.assertEqual(document["token_endpoint_auth_methods_supported"], ["none"])

    def test_register(self):
        response = self._register(
            redirect_uris=[CALLBACK, "http://localhost/callback"],
        )
        self.assertEqual(response.status_code, 201)
        payload = response.json()
        self.assertTrue(payload["client_id"])
        self.assertEqual(payload["token_endpoint_auth_method"], "none")

    def test_register_rejects_foreign_host(self):
        response = self._register(redirect_uris=["https://evil.com/callback"])
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"], "invalid_redirect_uri")

    def test_full_flow(self):
        client_id = self._register().json()["client_id"]
        location = self._authorize(client_id)
        query = parse_qs(urlparse(location).query)
        self.assertEqual(query["state"], ["test-state"])
        code = query["code"][0]
        response = self._exchange(client_id, code)
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["token_type"], "Bearer")
        self.assertEqual(payload["scope"], "mcp:read mcp:write")
        self.assertTrue(payload["refresh_token"])
        self.assertEqual(response.headers.get("Cache-Control"), "no-store")
        # The access token authenticates against the MCP endpoint as admin.
        mcp_response = self._mcp_initialize(payload["access_token"])
        self.assertEqual(mcp_response.status_code, 200)
        # Authorization codes are single use.
        retry = self._exchange(client_id, code)
        self.assertEqual(retry.status_code, 400)
        self.assertEqual(retry.json()["error"], "invalid_grant")

    def test_wrong_verifier(self):
        client_id = self._register().json()["client_id"]
        location = self._authorize(client_id)
        code = parse_qs(urlparse(location).query)["code"][0]
        response = self._exchange(client_id, code, verifier="wrong-verifier-still-long-enough")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"], "invalid_grant")

    def test_redirect_uri_mismatch_on_exchange(self):
        client_id = self._register(
            redirect_uris=[CALLBACK, "https://claude.ai/other"],
        ).json()["client_id"]
        location = self._authorize(client_id)
        code = parse_qs(urlparse(location).query)["code"][0]
        response = self._exchange(client_id, code, redirect_uri="https://claude.ai/other")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"], "invalid_grant")

    def test_deny(self):
        client_id = self._register().json()["client_id"]
        location = self._authorize(client_id, decision="deny")
        query = parse_qs(urlparse(location).query)
        self.assertEqual(query["error"], ["access_denied"])
        self.assertEqual(query["state"], ["test-state"])

    def test_missing_code_challenge(self):
        client_id = self._register().json()["client_id"]
        self.authenticate("admin", "admin")
        params = self._authorize_params(client_id, code_challenge="")
        response = self.url_open(f"/oauth2/authorize?{urlencode(params)}", allow_redirects=False)
        self.assertIn(response.status_code, (302, 303))
        query = parse_qs(urlparse(response.headers["Location"]).query)
        self.assertEqual(query["error"], ["invalid_request"])

    def test_unknown_client(self):
        self.authenticate("admin", "admin")
        params = self._authorize_params("not-a-client")
        response = self.url_open(f"/oauth2/authorize?{urlencode(params)}")
        self.assertEqual(response.status_code, 400)

    def test_unregistered_redirect_uri(self):
        client_id = self._register().json()["client_id"]
        self.authenticate("admin", "admin")
        params = self._authorize_params(client_id, redirect_uri="https://claude.ai/not-registered")
        response = self.url_open(f"/oauth2/authorize?{urlencode(params)}")
        self.assertEqual(response.status_code, 400)

    def test_unsupported_grant(self):
        client_id = self._register().json()["client_id"]
        response = self.url_open(
            "/oauth2/token",
            data={"grant_type": "client_credentials", "client_id": client_id},
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"], "unsupported_grant_type")

    def _issue_tokens(self):
        client_id = self._register().json()["client_id"]
        location = self._authorize(client_id)
        code = parse_qs(urlparse(location).query)["code"][0]
        return client_id, self._exchange(client_id, code).json()

    def test_refresh_grant(self):
        client_id, payload = self._issue_tokens()
        response = self.url_open(
            "/oauth2/token",
            data={
                "grant_type": "refresh_token",
                "client_id": client_id,
                "refresh_token": payload["refresh_token"],
            },
        )
        self.assertEqual(response.status_code, 200)
        rotated = response.json()
        self.assertNotEqual(rotated["access_token"], payload["access_token"])
        self.assertNotEqual(rotated["refresh_token"], payload["refresh_token"])
        # The new access token works, the old one is dead.
        self.assertEqual(self._mcp_initialize(rotated["access_token"]).status_code, 200)
        self.assertEqual(self._mcp_initialize(payload["access_token"]).status_code, 401)
        # Rotation: the old refresh token stops working in the same response.
        retry = self.url_open(
            "/oauth2/token",
            data={
                "grant_type": "refresh_token",
                "client_id": client_id,
                "refresh_token": payload["refresh_token"],
            },
        )
        self.assertEqual(retry.status_code, 400)
        self.assertEqual(retry.json()["error"], "invalid_grant")

    def test_revoke_endpoint(self):
        __, payload = self._issue_tokens()
        self.assertEqual(self._mcp_initialize(payload["access_token"]).status_code, 200)
        response = self.url_open("/oauth2/revoke", data={"token": payload["access_token"]})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self._mcp_initialize(payload["access_token"]).status_code, 401)
        # RFC 7009: unknown tokens do not leak validity.
        self.assertEqual(
            self.url_open("/oauth2/revoke", data={"token": "unknown-token"}).status_code,
            200,
        )

    def test_rate_limit(self):
        self.env["ir.config_parameter"].sudo().set_param("muk_mcp_oauth.endpoint_rate_limit", "2")
        for __ in range(3):
            response = self._register()
        # The in-memory bucket may already hold hits from earlier tests, so
        # only the final request is asserted.
        self.assertEqual(response.status_code, 429)
        self.assertEqual(response.json()["error"], "temporarily_unavailable")

    def test_revoked_token_gets_401(self):
        client_id = self._register().json()["client_id"]
        location = self._authorize(client_id)
        code = parse_qs(urlparse(location).query)["code"][0]
        access_token = self._exchange(client_id, code).json()["access_token"]
        self.assertEqual(self._mcp_initialize(access_token).status_code, 200)
        token = self.env["muk_mcp.oauth.token"].search(
            [("access_token_hash", "=", self.env["muk_mcp.key"]._hash_key(access_token))]
        )
        token.action_revoke()
        self.assertEqual(self._mcp_initialize(access_token).status_code, 401)
