# MuK MCP OAuth

OAuth 2.1 authorization server for the MCP endpoint, enabling the
zero-config custom connector experience on claude.ai web and mobile
apps: add the URL, log in to Odoo, authorize.

It implements:

- Protected Resource Metadata (RFC 9728) and Authorization Server
  Metadata (RFC 8414) well-known documents.
- Dynamic Client Registration (RFC 7591) for public clients, restricted
  to claude.ai / claude.com and loopback redirect URIs.
- Authorization code grant with mandatory PKCE S256 (OAuth 2.1) and a
  QWeb consent screen on top of the standard Odoo login.
- Form-urlencoded token endpoint issuing 60-minute access tokens and
  30-day refresh tokens with mandatory rotation (OAuth 2.1) and a hard
  180-day cap on the whole refresh chain, plus a revocation endpoint
  (RFC 7009).
- Bearer resolver integration: each access token is materialized as a
  `muk_mcp.key`, so scope gating (`mcp:read`/`mcp:write`), rate limiting
  and audit logging keep working unchanged, and the token executes as
  the user who authorized. Expiration and revocation are enforced on top
  by inheritance.
- An "OAuth Connections" list in the user preferences (Account Security)
  with a per-connection revoke button, purge crons for codes, tokens and
  idle DCR clients, and per-IP rate limiting on the public endpoints.

## Configuration

No configuration is required: installing the module publishes the OAuth
endpoints. Make sure that:

- `web.base.url` points to the public HTTPS URL of the instance (it is
  used as the OAuth issuer and to build every endpoint URL).
- The reverse proxy forwards `/.well-known/oauth-protected-resource*`,
  `/.well-known/oauth-authorization-server` and `/oauth2/*` to Odoo
  (some proxies reserve `/.well-known/` for ACME challenges).
- The instance is reachable from Anthropic's cloud (claude.ai and the
  mobile apps connect from Anthropic infrastructure, not from the
  device).

Optional: the `muk_mcp_oauth.endpoint_rate_limit` system parameter caps
requests per IP per minute on the public OAuth endpoints (default 60,
0 disables; the counter is per Odoo worker).

## Usage

On claude.ai: **Settings > Connectors > Add custom connector** and enter
`https://<instance>/mcp`. Claude discovers the OAuth metadata, registers
itself, opens the Odoo login and shows the consent screen. After
authorizing, the MCP tools run as your Odoo user with the granted scope
(`mcp:read` / `mcp:write`). The same instructions are shown in the
**Connect AI** wizard under the new **Claude Online** tab.

To test the flow manually, use the MCP Inspector:

    npx @modelcontextprotocol/inspector

Enter the MCP URL and pick "Quick OAuth Flow" in the Auth settings.

To revoke a connection, use the "OAuth Connections" list in your user
preferences (Account Security) and hit its Revoke button: the next
request returns 401 and Claude re-authenticates.
