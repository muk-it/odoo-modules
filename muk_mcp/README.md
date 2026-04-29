# MuK MCP Server

Implements a native MCP (Model Context Protocol) server inside Odoo,
exposing business data and operations to any MCP-compatible AI client.
The server speaks MCP Streamable HTTP at a single `/mcp` endpoint
using Bearer token authentication (Odoo API keys or dedicated MCP keys).

Compatible clients include Claude Desktop, Claude Code, OpenCode,
Cursor, Windsurf, Codex CLI, and any tool that supports the MCP
Streamable HTTP transport.

## Configuration

**Creating an MCP Key**

1. Log in to Odoo and navigate to your user preferences
   (**Settings > Users > Preferences**).
2. In the **Account Security** tab, click **Add MCP Key**.
3. Enter a description (e.g. "Claude Code") and pick a **Scope**
   (*Read Only* or *Read & Write*).
4. Click **Generate Key** and copy the key immediately -- it will not
   be shown again.

**Server Settings**

Navigate to **Settings > General Settings > MCP Server** to configure:

- **Session Timeout** -- Hours after which inactive MCP sessions are
  cleaned up (default: 24).
- **Log Retention** -- Days after which audit log entries are
  automatically deleted (default: 30).

**API Key Scopes**

Each MCP key has a scope that gates which tool categories it can
call: *Read Only* keys can call tools declared with `category='read'`,
*Read & Write* keys can call both. Scope enforcement happens before
the tool executes; Odoo's record rules and model ACLs still apply
on top, so a key can never exceed the permissions of its owning user.

**Rate Limiting**

Each key has a configurable rate limit (requests per minute). Set to
0 for unlimited. The default is 60 requests per minute.

## Client Setup

The MCP server endpoint is `https://<your-odoo>/mcp`. All clients
authenticate via a Bearer token -- either a dedicated MCP key (created
in user preferences) or a standard Odoo API key with `rpc` scope.

**Claude Code**

```bash
claude mcp add odoo \
  --transport http \
  --url https://your-odoo.com/mcp \
  --header "Authorization: Bearer YOUR_MCP_KEY"
```

Or add it directly to your `claude_code_config.json`:

```json
{
  "mcpServers": {
    "odoo": {
      "type": "url",
      "url": "https://your-odoo.com/mcp",
      "headers": {
        "Authorization": "Bearer YOUR_MCP_KEY"
      }
    }
  }
}
```

**Claude Desktop**

Add to your `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "odoo": {
      "type": "url",
      "url": "https://your-odoo.com/mcp",
      "headers": {
        "Authorization": "Bearer YOUR_MCP_KEY"
      }
    }
  }
}
```

**OpenCode**

Add the server to your `.opencode/config.json` or `opencode.json`:

```json
{
  "mcp": {
    "odoo": {
      "type": "remote",
      "url": "https://your-odoo.com/mcp",
      "headers": {
        "Authorization": "Bearer YOUR_MCP_KEY"
      }
    }
  }
}
```

**Cursor**

Add to your `.cursor/mcp.json`:

```json
{
  "mcpServers": {
    "odoo": {
      "url": "https://your-odoo.com/mcp",
      "headers": {
        "Authorization": "Bearer YOUR_MCP_KEY"
      }
    }
  }
}
```

**Codex CLI**

```bash
export MCP_ODOO_URL="https://your-odoo.com/mcp"
export MCP_ODOO_KEY="YOUR_MCP_KEY"

codex --mcp-server "odoo=$MCP_ODOO_URL" \
      --mcp-header "odoo=Authorization: Bearer $MCP_ODOO_KEY"
```

**cURL (testing)**

```bash
curl -X POST https://your-odoo.com/mcp \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_MCP_KEY" \
  -d '{
    "jsonrpc": "2.0",
    "id": 1,
    "method": "initialize",
    "params": {}
  }'
```

## Playground

The module ships with an in-backend **Playground** for testing tools
without hooking up an external MCP client. Open
**Settings > Technical > MCP > Playground** to access it.

The Playground:

- Lists every registered tool (Python- and database-backed) grouped
  by scope, with the same schemas the MCP `tools/list` method
  returns.
- Auto-renders a form for each tool's input schema so you can fill
  arguments without hand-writing JSON.
- Executes tools against the real `/mcp` endpoint using a
  Bearer-authenticated session — either a key you paste in
  (`Use existing`) or one generated in-place (`Generate new`).
- Displays the response, HTTP status, and round-trip time, plus a
  raw JSON-RPC view.
- Provides **Copy curl** and **Copy JSON-RPC** helpers for
  reproducing any call from the terminal or another client.

Keys entered or generated in the Playground are stored only in the
current tab's `sessionStorage`; nothing plaintext is persisted
server-side after generation. Press `Ctrl`+`Enter` in the detail
pane to run the current tool.

## Usage

Once connected, the AI client automatically discovers all available
tools via the `tools/list` MCP method. The module ships with 17
built-in tools organized into two categories:

**Read Tools (12)**

- `list_models` -- Discover available Odoo models by substring search.
- `list_modules` -- List installed modules with versions and states.
- `describe_model` -- Get complete field definitions for any model
  (types, labels, relations, selection values).
- `whoami` -- Retrieve the authenticated user's name, company,
  language, timezone, and security groups.
- `get_access_rights` -- Check the current user's CRUD permissions on a
  model and list all access control rules.
- `search_read` -- Search records by domain and return field values with
  pagination and sorting.
- `read_records` -- Read specific records by their database IDs.
- `search_count` -- Count records matching a domain filter.
- `read_group` -- Grouped aggregation (SQL GROUP BY equivalent) with
  automatic sum/count for numeric fields.
- `get_messages` -- Retrieve chatter history, comments, and field
  tracking for a record.
- `print_report` -- Render an `ir.actions.report` (PDF, text, HTML) for
  one or more records and return the binary as base64. Accepts the
  report xmlid, `report_name`, or numeric id.
- `export_records` -- Export records to CSV or XLSX (base64). Field
  paths use `/` to traverse relations (e.g. `partner_id/name`,
  `order_line/product_id/default_code`). Honours record rules and
  field access through Odoo's `export_data`.

**Write Tools (5)**

- `create_records` -- Create new records with support for relational
  field command tuples.
- `update_records` -- Update existing records by ID (partial writes).
- `delete_records` -- Permanently delete records by ID.
- `post_message` -- Post comments or internal notes on a record's
  chatter thread.
- `call_method` -- Call any public method on a model or recordset
  (private methods starting with `_` are blocked for safety).

## Extending the Tool Set

There are two ways to add tools. Choose based on audience:

- **Python tools** (`@mcp_tool` decorator) -- the recommended path for
  Odoo developers shipping tools inside their own addons. Code lives in
  your module, is version-controlled, testable, and runs without the
  `safe_eval` sandbox overhead.
- **UI tools** (database-backed) -- for administrators or power users
  who want to add ad-hoc tools without deploying code.

Both coexist. If a database tool has the same name as a decorated
method tool, the database tool shadows the method tool (useful for
runtime overrides during development).

### Python Tools -- From Other Addons

Any Odoo addon can register MCP tools by inheriting `muk_mcp.mixin`
and decorating public methods with `@mcp_tool`. The muk_mcp scanner
walks the mixin's MRO at worker startup and exposes every decorated
method automatically -- no explicit registration call needed.

Step 1 -- declare the dependency in your `__manifest__.py`:

```python
{
    'name': 'My Sales Tools',
    'depends': ['muk_mcp', 'sale'],
    ...
}
```

Step 2 -- extend `muk_mcp.mixin` and decorate your methods:

```python
# my_sale_mcp/models/mcp_tools.py
from odoo import api, models

from odoo.addons.muk_mcp.core.tool import mcp_tool


class MCPMixin(models.AbstractModel):
    _inherit = 'muk_mcp.mixin'

    @api.model
    @mcp_tool(
        name='confirm_sale_order',
        description=(
            'Confirm a quotation by ID. Transitions the order from '
            "'draft' to 'sale' and generates the delivery."
        ),
        input_schema={
            'type': 'object',
            'properties': {
                'id': {
                    'type': 'integer',
                    'description': 'sale.order record ID.',
                },
            },
            'required': ['id'],
        },
        category='write',
    )
    def confirm_sale_order(self, id):
        order = self.env['sale.order'].browse(id)
        order.action_confirm()
        return {'id': order.id, 'state': order.state}
```

Step 3 -- restart or upgrade the module. The tool appears in the next
`tools/list` response from any MCP client.

**Decorator reference**

`@mcp_tool(name=None, description=None, input_schema=None, category='read', registry=None)`

- `name` -- MCP tool name exposed to the AI client. Defaults to the
  Python method name. Must be unique across all installed addons.
- `description` -- Human-readable explanation shown to the AI. When
  omitted, the first line of the method's docstring is used.
- `input_schema` -- JSON Schema object describing the tool arguments.
  When omitted, an empty-object schema is used. Keys in `properties`
  become kwargs on the method call.
- `category` -- `'read'` or `'write'`. Read-scoped MCP keys can only
  call `'read'` tools; write-scoped keys call both.
- `registry` -- Optional surface restriction. Leave empty (the usual
  case) so the tool is visible to every caller. Set to `'mcp'` to
  hide the tool from other surfaces, or to a downstream value like
  `'ai'` (added by `muk_ai`) to target a specific agent. Callers pass
  a `registry=` argument to `get_tools()` / `get_tool_index()` to
  filter. Comma-separated values are supported for multi-surface
  tools (e.g. `registry='mcp,cron'`).

**How arguments flow**

1. The MCP client sends `tools/call` with a JSON `arguments` dict.
2. `muk_mcp.tool._call` pops any `context` key, merges it into
   `self.env.context`, then invokes the decorated method with the
   remaining keys as keyword arguments.
3. The return value is serialized via `RecordEncoder` (recordsets
   become `[(id, display_name), ...]`; datetimes and bytes are
   coerced to strings).
4. Raising `UserError` or `AccessError` bubbles the message back
   to the AI client as a tool error.

**Helpers available on `muk_mcp.mixin`**

Because your class inherits the mixin, you get two small helpers for
free:

- `self._resolve_model(name)` -- returns `self.env[name]` and raises
  `UserError` if the model does not exist.
- `self._normalize_ids(ids)` -- accepts `None`, a single int, or a
  list of ints; always returns a list.

**Testing your tools**

Call `muk_mcp.tool._call` directly from a `TransactionCase`:

```python
from odoo.tests import common


class TestMySaleTools(common.TransactionCase):

    def test_confirm_sale_order(self):
        order = self.env['sale.order'].create({...})
        text, info = self.env['muk_mcp.tool']._call(
            'confirm_sale_order', {'id': order.id}, self.env,
        )
        self.assertEqual(info['res_id'], order.id)
        self.assertEqual(order.state, 'sale')
```

The second return value is a `record_info` dict (`res_id` /
`res_ids`) used by the audit log; ignore it if you don't need it.

### UI Tools -- From the Admin Backend

Additional tools can be created through the backend UI at
**Settings > MCP Server > Tools**. Each tool consists of:

- A name and description (exposed to the AI client).
- A JSON Schema defining the input parameters.
- Python code executed in a sandboxed `safe_eval` context with access
  to `env`, `arguments`, `json`, `UserError`, and `logger`.

Tools are categorized as Read or Write and can be enabled/disabled
individually. When a UI tool shares a name with a Python tool, the UI
tool wins -- useful for overriding decorator tools at runtime without
redeploying code.

**Audit Log**

Every MCP request is logged with the method, tool name, target model,
duration, and status (ok, error, denied, rate_limited). Logs are
accessible at **Settings > MCP Server > Audit Log** and are automatically
cleaned up based on the configured retention period.

**Sessions**

The server maintains stateful sessions per the MCP specification.
Active sessions are visible at **Settings > MCP Server > Sessions** (in
debug mode) and can be revoked from user preferences. Sessions are
automatically cleaned up after the configured timeout.
