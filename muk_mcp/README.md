# MuK MCP Server

[![Odoo 20.0](https://img.shields.io/badge/Odoo-20.0-714B67?style=flat-square)](https://apps.odoo.com/apps/modules/muk_mcp)
![Community](https://img.shields.io/badge/CE-%E2%9C%93-1C3A4C?style=flat-square)
![Enterprise](https://img.shields.io/badge/EE-%E2%9C%93-33627E?style=flat-square)
![Odoo.sh](https://img.shields.io/badge/Odoo.sh-%E2%9C%93-1C3A4C?style=flat-square)
![On-Premise](https://img.shields.io/badge/On--Premise-%E2%9C%93-33627E?style=flat-square)
[![License LGPL v3](https://img.shields.io/badge/License-LGPL_v3-blue?style=flat-square)](LICENSE)
[![YouTube demo](https://img.shields.io/badge/YouTube-demo-FF0000?style=flat-square&logo=youtube&logoColor=white)](https://youtu.be/05wTnenU-LU)
[![Website mukit.at](https://img.shields.io/badge/Website-mukit.at-243742?style=flat-square)](https://www.mukit.at)

Implements an MCP (Model Context Protocol) server inside Odoo. AI clients such
as Claude Code, Claude Desktop, Codex, Cursor and OpenCode connect to the
`/api/mcp` endpoint with an MCP key and work with the database through tools,
prompts and resources, with the access rights of the user the key belongs to.
Every call is recorded in an audit log.

## Configuration

**MCP Keys**

Every request is authenticated with an MCP key, sent as a bearer token. A
user creates their own keys in their preferences (**Account Security** tab,
**Add MCP Key**): a name, a **Scope** (_Read Only_ or _Read & Write_) and a
rate limit in requests per minute, `0` for unlimited. The key is shown once
and stored as a hash. Administrators see every key under
**Settings > MCP > Authentication > API Keys**.

A _Read Only_ key calls read tools only; a write tool is refused and logged
as denied. Record rules and access rights apply on top, so a key never
exceeds the rights of its user. The keys of an archived user stop working.

**Server Settings**

**Settings > General Settings > MCP Server** sets:

- **Log Retention**: days after which audit log entries are deleted.
- **Rate Limiting**: the default rate limit for new keys.
- **Annotate Messages**: mark chatter messages written through MCP.

The configuration file accepts `mcp_logging = False` to stop writing the
audit log, and `mcp_debug = True` to add the traceback to internal errors.

**Connecting a Client**

**Settings > MCP > Connect** shows the server address and a ready-made
configuration for Claude Code, Claude Desktop, Codex CLI, OpenCode and
Cursor. **Generate Bearer Key** creates a key and fills it into every
snippet. The address is `https://<your-odoo>/api/mcp`; on Enterprise,
`/mcp` belongs to Odoo's own MCP server and both run side by side.

Claude Code:

```bash
claude mcp add --transport http odoo https://your-odoo.com/api/mcp --header "Authorization: Bearer YOUR_MCP_KEY"
```

Claude Desktop, through `mcp-remote` (`claude_desktop_config.json`):

```json
{
    "mcpServers": {
        "odoo": {
            "command": "npx",
            "args": [
                "-y",
                "mcp-remote",
                "https://your-odoo.com/api/mcp",
                "--header",
                "Authorization: Bearer YOUR_MCP_KEY"
            ]
        }
    }
}
```

Codex CLI (`~/.codex/config.toml`):

```toml
[mcp_servers.odoo]
url = "https://your-odoo.com/api/mcp"
headers.Authorization = "Bearer YOUR_MCP_KEY"
```

Cursor (`.cursor/mcp.json`):

```json
{
    "mcpServers": {
        "odoo": {
            "url": "https://your-odoo.com/api/mcp",
            "headers": { "Authorization": "Bearer YOUR_MCP_KEY" }
        }
    }
}
```

OpenCode (`opencode.json`):

```json
{
    "mcp": {
        "odoo": {
            "type": "remote",
            "url": "https://your-odoo.com/api/mcp",
            "enabled": true,
            "headers": { "Authorization": "Bearer YOUR_MCP_KEY" }
        }
    }
}
```

Any other client that speaks MCP over Streamable HTTP connects the same way.
To try the endpoint from a terminal, with the key in `$MCP_KEY`:

```bash
curl https://your-odoo.com/api/mcp \
  -H "Authorization: Bearer $MCP_KEY" \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc": "2.0", "id": 1, "method": "tools/list"}'
```

**Multi-database Hosts**

On a host that serves several databases, the client names its database in
the `X-Odoo-Database` header, which Odoo resolves before the request is
dispatched. A host with one database per domain (`dbfilter = ^%h$` or
`db_name`) needs nothing.

**Allowed Origins**

A request that carries an `Origin` header is checked against an allow-list,
to guard against DNS rebinding; one from an origin that is not allowed is
answered `403`. Requests without an `Origin` header, which is what desktop
and command-line clients send, pass. The instance's own base URL is always
allowed. Add more with the `muk_mcp.allowed_origins` system parameter
(comma-separated), or set `muk_mcp.allow_any_origin` to `True` to turn the
check off.

## Usage

**Protocol**

The endpoint answers JSON-RPC posted to `/api/mcp`, one message per request,
and keeps no session: it issues no `Mcp-Session-Id`, opens no event stream
and announces no list changes. Each request is identified by its key alone.

It serves the stateless revision `2026-07-28`, with `server/discover`, and
the handshake revisions `2025-11-25` and `2025-06-18`, with `initialize` and
`ping`. The revision is read from the request's `_meta` and the
`MCP-Protocol-Version` header, which must agree; a request with neither is
served as `2025-11-25`. On `2026-07-28` a request carries the
`MCP-Protocol-Version` and `Mcp-Method` headers, `Mcp-Name` for
`tools/call`, `prompts/get` and `resources/read`, and the protocol version
and client capabilities in `_meta`.

A notification is answered `202`, a missing or unknown key `401`, a key
past its rate limit `429`, and a version, header or parameter fault `400`.
A failing tool is a tool result with `isError`, not a protocol error.

**Tools**

Clients discover the tools through `tools/list`. Read tools carry the
`readOnlyHint` annotation.

Read tools:

- `list_models`, `describe_model`: find models and read their fields, with
  types, labels, relations and selection values.
- `search_read`, `read_records`, `search_count`, `read_group`: search, read,
  count and aggregate records.
- `get_messages`: the chatter of a record, with comments and tracking.
- `print_report`: render a report as PDF, HTML or text, returned as base64.
- `export_records`: export records to CSV or XLSX through Odoo's export,
  with `/` field paths such as `partner_id/name`.
- `read_resource`: read a file by its `odoo://` URI.
- `authorize_download`: a one-time link to fetch a file with an HTTP
  GET, so it never passes through the conversation.
- `whoami`, `get_access_rights`: the key's user, company, language and
  groups, and the user's rights on a model.
- `system_info`, `list_modules`, `list_languages`: the server, the installed
  modules and the installed languages.

Write tools:

- `create_records`, `update_records`, `delete_records`: write records,
  relational fields as Odoo command lists.
- `post_message`: post a message or an internal note on a record.
- `schedule_activity`: schedule an activity on a record, by type name,
  for a user and a due date.
- `upload_file`: put a file into a binary field or onto a record as an
  attachment, from an `authorize_upload` file or as base64.
- `authorize_upload`: a one-time link the client sends the raw file to
  with an HTTP PUT, so the file never passes through the conversation.
- `call_method`: call a public method on a model or on records. Methods
  starting with `_` are refused.

Every tool accepts a `context` argument that is merged into the
environment, for example `{"lang": "de_DE"}` or
`{"allowed_company_ids": [1]}`.

**Resources**

`search_read` and `read_records` return binary fields as
`odoo://record/<model>/<id>/<field>` URIs instead of base64. A client reads
the file when it needs it, through `read_resource` or `resources/read`.
`odoo://attachment/<id>` addresses an attachment. Text comes back as text,
images and audio as typed content, anything else as a base64 blob; indexed
documents can also be read as their extracted text.

**Prompts**

Prompts are templates the user picks in the client, often as a slash command
(`/mcp__odoo__summarize_record` in Claude Code). The module ships
`summarize_record` and `activities_today`. An argument named `model` is
completed with matching model names through `completion/complete`.

**Playground**

**Settings > MCP > Catalog > Playground** runs tools and prompts without an
external client. Paste a key (**Use existing**) or create one
(**Generate new**); it is kept in the browser tab's session storage only.
Each tool shows a form built from its schema, the raw schema, and after
**Try it** (`Ctrl` + `Enter`) the HTTP status, the duration and the answer.
**curl** and **JSON-RPC** copy the call for a terminal or another client.
The **Prompts** panel fills a prompt's arguments, with completion, and shows
the messages it expands to.

**Audit Log**

**Settings > MCP > Logging > Audit Log** lists every call with its key,
user, method, tool, model, record, duration, IP address, request, response
and status (_OK_, _Error_, _Denied_, _Rate Limited_). Entries older than the
retention period are deleted automatically.

**Messages Written over MCP**

With **Annotate Messages** on, a chatter message created during an MCP call,
posted or tracked, carries an **MCP** badge whose tooltip names the key.

## Extending

**Python Tools and Prompts**

An addon that depends on `muk_mcp` inherits `muk_mcp.mixin` and decorates
methods; they are listed once the addon is installed.

```python
from odoo import api, models

from odoo.addons.muk_mcp.core.prompt import mcp_prompt
from odoo.addons.muk_mcp.core.tool import mcp_tool


class MCPMixin(models.AbstractModel):
    _inherit = 'muk_mcp.mixin'

    @api.model
    @mcp_tool(
        name='confirm_sale_order',
        description='Confirm a quotation by its id.',
        input_schema={
            'type': 'object',
            'properties': {'id': {'type': 'integer'}},
            'required': ['id'],
        },
        category='write',
    )
    def _mcp_confirm_sale_order(self, id):
        order = self.env['sale.order'].browse(id)
        order.action_confirm()
        return {'id': order.id, 'state': order.state}

    @api.model
    @mcp_prompt(
        name='review_order',
        title='Review an order',
        arguments=[{'name': 'record_id', 'required': True}],
    )
    def _mcp_prompt_review_order(self, record_id):
        return f'Read sale.order {record_id} and list anything that blocks it.'
```

`@mcp_tool(name, description, input_schema, category, registry)`: `name`
defaults to the method name and `description` to the first docstring line;
the keys of `input_schema` arrive as keyword arguments; `category` is
`'read'` or `'write'`; `registry='mcp'` limits the tool to MCP clients when
other surfaces read the same tool index. The return value is serialised to
JSON (recordsets as `[id, display_name]` pairs); a `UserError` or
`AccessError` reaches the client as a tool error.

`@mcp_prompt(name, title, description, arguments)` returns the prompt text
or a list of messages; required arguments are checked before the method
runs.

The mixin offers `self._resolve_model(name)`, and
`odoo.addons.muk_mcp.tools.parser` offers `normalize_ids()` and
`coerce_json_value()` for loosely typed input. A tool is tested through
`self.env['muk_mcp.tool']._call(name, arguments, self.env)`.

**Tools and Prompts as Records**

**Settings > MCP > Catalog > Tools** and **Prompts** hold tools and prompts
written in the backend: a name, a description, an input schema or argument
list, and Python run in a `safe_eval` sandbox with `env`, `arguments`,
`json`, `UserError` and `logger`, which sets `result`. A record with the
name of a Python tool or prompt takes its place.
