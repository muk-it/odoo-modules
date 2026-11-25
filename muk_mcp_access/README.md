# MuK MCP Access

Model-level access control for the MuK MCP Server. Restricts which Odoo
models AI agents can discover and operate on through the Model Context
Protocol, independent of the user's normal access rights.

Requires [MuK MCP Server](https://apps.odoo.com/apps/modules/muk_mcp).

## Configuration

Navigate to **Settings > MCP > Model Access** to manage the whitelist.

- **Empty list** -- every model is accessible (backwards-compatible
  default).
- **Non-empty list** -- only listed models are exposed to MCP clients.

Each entry controls:

- **Read** -- model is visible in `list_models` and queryable via
  `search_read`, `read_records`, `describe_model`, etc.
- **Write** -- model is writable via `create_records`,
  `update_records`, `delete_records`, and `call_method`.
- **Ask** -- the user is asked in the AI client before
  a write tool runs on the model. A client that cannot ask is refused.

Use the _Add Models_ button to bulk-enable multiple models at once.
The wizard excludes transient models and models already in the
access list.

## Usage

Once the whitelist contains at least one entry, the module enforces
three restrictions:

1. **Tool-level blocking** -- any tool that accepts a `model`
   argument (`search_read`, `create_records`, `describe_model`,
   etc.) raises `AccessError` when the model is not in the
   whitelist or the operation is not allowed.

2. **Discovery filtering** -- `list_models` only returns models
   that appear in the whitelist, so the AI client cannot discover
   restricted models.

3. **Resource blocking** -- `read_resource` resolves the record an
   `odoo://attachment/<id>` uri belongs to and raises `AccessError`
   when that model is not whitelisted or the record falls outside
   the configured record domain. Attachments linked to no record,
   and those on models a module declares as MCP payload carriers,
   stay readable.

`call_method` is covered too. A method called on record ids checks
those ids against the record domain; a model-level method
(`search_read`, `web_search_read`, `create`, ...) gets the record
domain merged into its `domain` argument, and any record it returns
is checked against the domain, the call being rolled back otherwise.

When a model asks before changes, the first call of a write tool
changes nothing and returns a question with the tool, its arguments and
the records it names. The client shows it and repeats the call with the
answer. An accepted change is written, once: the answer is bound to the
user, the key, the tool and its arguments, and expires after 15 minutes.
A declined change comes back as an error the agent can report. Asking
needs the protocol revision `2026-07-28` and a client with the
elicitation capability, for example Claude Code; any other client is
refused. The confirmation guards against mistakes. The client reports the
answer, so it is no substitute for access rights or a read-only key.

The check respects the tool's category: read tools check
`allow_read`, write tools check `allow_write`. This layering
works alongside MCP API key scopes (read-only keys, rate limits)
and Odoo's built-in record rules and model ACLs.
