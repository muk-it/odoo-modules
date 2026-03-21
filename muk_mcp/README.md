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
3. Enter a description (e.g. "Claude Code") and optionally restrict
   access to specific models via **Model Scopes**.
4. Click **Generate Key** and copy the key immediately -- it will not
   be shown again.

**Server Settings**

Navigate to **Settings > General Settings > MCP Server** to configure:

- **Session Timeout** -- Hours after which inactive MCP sessions are
  cleaned up (default: 24).
- **Log Retention** -- Days after which audit log entries are
  automatically deleted (default: 30).

**API Key Scopes**

Each MCP key can optionally be restricted to specific models with
fine-grained permissions (read, write, create, delete). Leave the
scope list empty to allow unrestricted access.

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

## Usage

Once connected, the AI client automatically discovers all available
tools via the `tools/list` MCP method. The module ships with 15
built-in tools organized into two categories:

**Read Tools (10)**

- `list_models` -- Discover available Odoo models by substring search.
- `list_modules` -- List installed modules with versions and states.
- `get_model_schema` -- Get complete field definitions for any model
  (types, labels, relations, selection values).
- `get_user_context` -- Retrieve the authenticated user's name, company,
  language, timezone, and security groups.
- `get_access_rights` -- Check the current user's CRUD permissions on a
  model and list all access control rules.
- `search_read` -- Search records by domain and return field values with
  pagination and sorting.
- `read_record` -- Read specific records by their database IDs.
- `search_count` -- Count records matching a domain filter.
- `read_group` -- Grouped aggregation (SQL GROUP BY equivalent) with
  automatic sum/count for numeric fields.
- `get_record_messages` -- Retrieve chatter history, comments, and field
  tracking for a record.

**Write Tools (5)**

- `create_record` -- Create new records with support for relational
  field command tuples.
- `update_record` -- Update existing records by ID (partial writes).
- `delete_record` -- Permanently delete records by ID.
- `post_message` -- Post comments or internal notes on a record's
  chatter thread.
- `execute_method` -- Call any public method on a model or recordset
  (private methods starting with `_` are blocked for safety).

**Custom Tools**

Additional tools can be created through the backend UI at
**Settings > MCP Server > Tools**. Each tool consists of:

- A name and description (exposed to the AI client).
- A JSON Schema defining the input parameters.
- Python code executed in a sandboxed `safe_eval` context with access
  to `env`, `arguments`, `json`, `UserError`, and `logger`.

Tools are categorized as Read or Write and can be enabled/disabled
individually.

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
