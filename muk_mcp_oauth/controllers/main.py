# Copyright 2026, Jarsa
# License LGPL-3.0 or later (http://www.gnu.org/licenses/lgpl.html).

import json
from urllib.parse import urlencode

from odoo import fields, http
from odoo.http import request

from odoo.addons.muk_mcp.tools.rate_limit import rate_limiter

from ..models.oauth_token import ACCESS_TTL_SECONDS

SCOPES = {
    "mcp:read": "Read data through the MCP tools",
    "mcp:write": "Create and modify data through the MCP tools",
}
DEFAULT_SCOPE = "mcp:read mcp:write"


class OAuthController(http.Controller):
    def _base_url(self):
        return request.env["ir.config_parameter"].sudo().get_param("web.base.url").rstrip("/")

    def _json(self, payload, status=200):
        response = request.make_json_response(payload, status=status)
        response.headers["Cache-Control"] = "no-store"
        return response

    # ----------------------------------------------------------
    # Metadata (RFC 9728 / RFC 8414)
    # ----------------------------------------------------------

    @http.route(
        [
            "/.well-known/oauth-protected-resource",
            "/.well-known/oauth-protected-resource/mcp",
        ],
        type="http",
        auth="none",
        methods=["GET"],
        csrf=False,
        cors="*",
    )
    def oauth_protected_resource(self, **kwargs):
        base_url = self._base_url()
        return self._json(
            {
                "resource": f"{base_url}/mcp",
                "authorization_servers": [base_url],
                "scopes_supported": list(SCOPES),
                "bearer_methods_supported": ["header"],
            }
        )

    @http.route(
        "/.well-known/oauth-authorization-server",
        type="http",
        auth="none",
        methods=["GET"],
        csrf=False,
        cors="*",
    )
    def oauth_authorization_server(self, **kwargs):
        base_url = self._base_url()
        return self._json(
            {
                "issuer": base_url,
                "authorization_endpoint": f"{base_url}/oauth2/authorize",
                "token_endpoint": f"{base_url}/oauth2/token",
                "registration_endpoint": f"{base_url}/oauth2/register",
                "response_types_supported": ["code"],
                "grant_types_supported": ["authorization_code", "refresh_token"],
                "code_challenge_methods_supported": ["S256"],
                "token_endpoint_auth_methods_supported": ["none"],
                "scopes_supported": list(SCOPES),
            }
        )

    # ----------------------------------------------------------
    # Dynamic Client Registration (RFC 7591)
    # ----------------------------------------------------------

    @http.route(
        "/oauth2/register",
        type="http",
        auth="none",
        methods=["POST"],
        csrf=False,
        cors="*",
    )
    def oauth_register(self, **kwargs):
        if not self._check_endpoint_rate_limit("register"):
            return self._json({"error": "temporarily_unavailable"}, status=429)
        try:
            data = json.loads(request.httprequest.get_data() or b"{}")
        except ValueError:
            return self._json({"error": "invalid_client_metadata"}, status=400)
        redirect_uris = data.get("redirect_uris") or []
        client_model = request.env["muk_mcp.oauth.client"].sudo()
        if not redirect_uris or not all(
            isinstance(uri, str) and client_model._is_uri_allowed(uri) for uri in redirect_uris
        ):
            return self._json(
                {
                    "error": "invalid_redirect_uri",
                    "error_description": "Only claude.ai/claude.com (https) and "
                    "loopback (http) redirect URIs are allowed.",
                },
                status=400,
            )
        client = client_model.create(
            {
                "client_name": (data.get("client_name") or "MCP Client")[:100],
                "redirect_uris": "\n".join(redirect_uris),
            }
        )
        return self._json(
            {
                "client_id": client.client_id,
                "client_name": client.client_name,
                "redirect_uris": redirect_uris,
                "token_endpoint_auth_method": "none",
                "grant_types": ["authorization_code", "refresh_token"],
                "response_types": ["code"],
            },
            status=201,
        )

    # ----------------------------------------------------------
    # Authorization endpoint (OAuth 2.1, PKCE S256 mandatory)
    # ----------------------------------------------------------

    def _find_client(self, params):
        """Validations that must NOT redirect (RFC 6749 §4.1.2.1): unknown
        client or unregistered redirect_uri render an error instead of
        sending the user to an attacker-supplied URI."""
        client = (
            request.env["muk_mcp.oauth.client"]
            .sudo()
            .search([("client_id", "=", params.get("client_id") or "")], limit=1)
        )
        if not client:
            return None, request.make_response("Unknown client_id", status=400)
        if not client._match_redirect_uri(params.get("redirect_uri") or ""):
            return None, request.make_response("Invalid redirect_uri", status=400)
        return client, None

    def _redirect_error(self, params, error):
        query = {"error": error}
        if params.get("state"):
            query["state"] = params["state"]
        redirect_uri = params["redirect_uri"]
        separator = "&" if "?" in redirect_uri else "?"
        return request.redirect(f"{redirect_uri}{separator}{urlencode(query)}", local=False)

    def _check_authorize_params(self, params):
        """Returns an error redirect response, or None when the request is
        a valid OAuth 2.1 authorization request."""
        if params.get("response_type") != "code":
            return self._redirect_error(params, "unsupported_response_type")
        if not params.get("code_challenge") or params.get("code_challenge_method") != "S256":
            return self._redirect_error(params, "invalid_request")
        scopes = (params.get("scope") or DEFAULT_SCOPE).split()
        if not all(scope in SCOPES for scope in scopes):
            return self._redirect_error(params, "invalid_scope")
        return None

    @http.route("/oauth2/authorize", type="http", auth="user", methods=["GET"])
    def oauth_authorize(self, **params):
        client, error_response = self._find_client(params)
        if error_response:
            return error_response
        if error_redirect := self._check_authorize_params(params):
            return error_redirect
        scope = params.get("scope") or DEFAULT_SCOPE
        form_params = {
            key: params.get(key) or ""
            for key in (
                "response_type",
                "client_id",
                "redirect_uri",
                "state",
                "code_challenge",
                "code_challenge_method",
            )
        }
        form_params["scope"] = scope
        return request.render(
            "muk_mcp_oauth.consent",
            {
                "client": client,
                "user": request.env.user,
                "scopes": [(scope, SCOPES[scope]) for scope in scope.split()],
                "form_params": form_params,
                "csrf_token": request.csrf_token(),
            },
        )

    @http.route("/oauth2/authorize", type="http", auth="user", methods=["POST"])
    def oauth_authorize_decision(self, **params):
        client, error_response = self._find_client(params)
        if error_response:
            return error_response
        if error_redirect := self._check_authorize_params(params):
            return error_redirect
        if params.get("decision") != "accept":
            return self._redirect_error(params, "access_denied")
        raw_code = (
            request.env["muk_mcp.oauth.code"]
            .sudo()
            ._issue(
                client,
                request.env.user,
                params.get("scope") or DEFAULT_SCOPE,
                params["code_challenge"],
                params["redirect_uri"],
            )
        )
        query = {"code": raw_code}
        if params.get("state"):
            query["state"] = params["state"]
        redirect_uri = params["redirect_uri"]
        separator = "&" if "?" in redirect_uri else "?"
        return request.redirect(f"{redirect_uri}{separator}{urlencode(query)}", local=False)

    # ----------------------------------------------------------
    # Token endpoint (RFC 6749 §4.1.3, form-urlencoded)
    # ----------------------------------------------------------

    def _token_error(self, error, description=None, status=400):
        payload = {"error": error}
        if description:
            payload["error_description"] = description
        return self._json(payload, status=status)

    def _parse_form(self):
        # RFC 6749 mandates application/x-www-form-urlencoded (Claude sends
        # exactly that); JSON is accepted as a courtesy fallback.
        form = request.httprequest.form
        if not form:
            try:
                form = json.loads(request.httprequest.get_data() or b"{}")
            except ValueError:
                form = None
        return form

    def _check_endpoint_rate_limit(self, endpoint):
        limit = int(request.env["ir.config_parameter"].sudo().get_param("muk_mcp_oauth.endpoint_rate_limit", 60))
        # The limiter is per worker process, so the effective limit is
        # roughly limit x workers.
        return rate_limiter.check(f"muk_mcp_oauth:{endpoint}:{request.httprequest.remote_addr}", limit, 60)

    def _token_response(self, token, access_raw, refresh_raw):
        token.client_id.write({"last_used": fields.Datetime.now()})
        return self._json(
            {
                "access_token": access_raw,
                "token_type": "Bearer",
                "expires_in": ACCESS_TTL_SECONDS,
                "refresh_token": refresh_raw,
                "scope": token.scope,
            }
        )

    def _grant_authorization_code(self, form, client):
        if not all(form.get(field) for field in ("code", "redirect_uri", "code_verifier")):
            return self._token_error("invalid_request", "code, redirect_uri and code_verifier are required.")
        code = (
            request.env["muk_mcp.oauth.code"]
            .sudo()
            ._consume(form["code"], client, form["redirect_uri"], form["code_verifier"])
        )
        if not code:
            return self._token_error("invalid_grant")
        token, access_raw, refresh_raw = (
            request.env["muk_mcp.oauth.token"].sudo()._issue(client, code.user_id, code.scope)
        )
        return self._token_response(token, access_raw, refresh_raw)

    def _grant_refresh_token(self, form, client):
        if not form.get("refresh_token"):
            return self._token_error("invalid_request", "refresh_token is required.")
        token, access_raw, refresh_raw = (
            request.env["muk_mcp.oauth.token"].sudo()._refresh(form["refresh_token"], client)
        )
        if not token:
            return self._token_error("invalid_grant")
        return self._token_response(token, access_raw, refresh_raw)

    @http.route(
        "/oauth2/token",
        type="http",
        auth="none",
        methods=["POST"],
        csrf=False,
        cors="*",
    )
    def oauth_token(self, **kwargs):
        if not self._check_endpoint_rate_limit("token"):
            return self._token_error("temporarily_unavailable", status=429)
        form = self._parse_form()
        if form is None:
            return self._token_error("invalid_request", "Malformed request body.")
        grants = {
            "authorization_code": self._grant_authorization_code,
            "refresh_token": self._grant_refresh_token,
        }
        grant = grants.get(form.get("grant_type"))
        if not grant:
            return self._token_error("unsupported_grant_type")
        client = (
            request.env["muk_mcp.oauth.client"].sudo().search([("client_id", "=", form.get("client_id") or "")], limit=1)
        )
        if not client:
            return self._token_error("invalid_client", status=401)
        return grant(form, client)

    # ----------------------------------------------------------
    # Revocation endpoint (RFC 7009)
    # ----------------------------------------------------------

    @http.route(
        "/oauth2/revoke",
        type="http",
        auth="none",
        methods=["POST"],
        csrf=False,
        cors="*",
    )
    def oauth_revoke(self, **kwargs):
        if not self._check_endpoint_rate_limit("revoke"):
            return self._token_error("temporarily_unavailable", status=429)
        form = self._parse_form()
        if form is None or not form.get("token"):
            return self._token_error("invalid_request", "token is required.")
        request.env["muk_mcp.oauth.token"].sudo()._revoke_value(form["token"])
        # RFC 7009 §2.2: 200 even when the token is unknown or already
        # revoked, to avoid leaking token validity.
        return self._json({})
