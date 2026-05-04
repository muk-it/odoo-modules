# MuK AI Skills

Pre-built agent skills your users (or the LLM itself) can switch into.
A **skill** is a DB-backed record bundling a name, a one-line
description for LLM discovery, a markdown body of instructions, and
optional file attachments. Visible skills are listed in a
system-prompt addendum so the agent can pick one autonomously, and
users can invoke them directly in chat with a `/<name>` slash command.

This addon plugs into `muk_ai`'s session runtime via `_inherit` only —
no fork of `muk_ai` or `muk_mcp` source.

## What's in the box

- **`muk_ai.skill` model** — name, label, description, markdown body,
  attached resources (`ir.attachment`), agent scoping (specific
  agents or global), prompt revision history (via the reusable
  `muk_ai.revision.mixin` from `muk_ai`).
- **`invoke_skill` MCP tool** — agent-callable, returns the skill
  body plus a resource manifest with `uri` entries the agent can
  fetch via `muk_mcp`'s generic `read_resource`.
- **System-prompt addendum** — every visible skill is listed by
  technical name + one-line description inside an
  `<available_skills>` block appended to the agent's system prompt.
- **Slash command in chat** — typing `/<skill_name>` in the composer
  fires the skill directly, mirroring the same `invoke_skill` flow
  the LLM uses but without an LLM round-trip.
- **Manage menu link** — *MuK AI > Skills* (and `/odoo/ai-skills`).

## How a skill is built

Open *MuK AI > Skills* and create a record:

- **Technical Name** — lowercase identifier matching `[a-z][a-z0-9_]*`,
  used for the `/name` slash command and in the LLM-facing addendum
  (e.g. `quote_followup`, `lead_brief`, `summarize_thread`).
- **Label** — human-readable name shown in lists, the chat menu, and
  the manage view. Optional; falls back to a title-cased version of
  the technical name.
- **Description** — one-line description shown to the LLM in the
  system-prompt addendum. The LLM uses this to decide *when* to invoke
  the skill autonomously.
- **Body** — markdown instructions returned when the skill is invoked.
  Treated as additional system-prompt content the agent should follow
  for the duration of the task. Edited with the same code widget as
  agent system prompts.
- **Resources** — attached files. Each one becomes a manifest entry
  with a stable `odoo://attachment/<id>` URI; the agent fetches the
  bytes by passing that URI to `read_resource`.
- **Agents** — leave empty to make the skill global, or pick one or
  more agents to scope visibility. Sessions only see skills whose
  agent scope matches (or skills with no scope).
- **Active / Sequence** — standard Odoo flags; sequence drives the
  order in the addendum and the slash-command popover.

Body edits snapshot the prior value into the skill's `prompt_history`
JSON column. The **History** stat button on the skill form opens a
side-by-side dialog listing every prior revision with author and
timestamp; restoring rolls back to that revision.

## How an agent uses a skill

When a session starts, `muk_ai_skills` walks the visible-skill set
for the session's agent and appends an `<available_skills>` block to
the system prompt:

```
<available_skills>
Named workflows you can invoke with the `invoke_skill` tool
(`{"skill_name": "<skill>"}`). Each returns a body of instructions
plus a resource manifest with `uri` entries (e.g.
`odoo://attachment/42`); fetch any listed resource with `read_resource`
(`{"uri": "<uri>"}`).

Pick a skill when its description matches the user request. Skills
are NOT tools — for tool discovery use <available_tools> + tool_load,
never invoke_skill.

- `quote_followup`: Draft a follow-up email for an open sales quote.
- `lead_brief`: Summarize a CRM lead with last touchpoint and next-best action.
- `summarize_thread`: Summarize a mail.thread chatter into ≤5 bullets.
</available_skills>
```

If the agent calls `invoke_skill(skill_name='quote_followup')`, the
tool returns:

```json
{
  "name": "quote_followup",
  "label": "Quote Follow-up",
  "body": "## Steps\n1. Look up the sale.order by ref or domain…",
  "resources": [
    {"name": "tone_guide.md", "uri": "odoo://attachment/42", "mimetype": "text/markdown"}
  ]
}
```

The agent treats the body as fresh instructions and reads any of the
listed resources via `read_resource(uri='odoo://attachment/42')` — no
new tool needed for that, the URI handler is in `muk_mcp`.

## How a user invokes a skill

Type `/` in the composer to open the slash-command popover. Built-in
commands (`/help`, `/clear`, `/compact`, `/unpin`) are merged with
the visible skills for the session. Picking `/quote_followup` (or
just typing it and hitting Enter) calls `invoke_skill_from_chat` on the
session, which:

1. Records a `tool_call` and matching `tool_result` in the session
   event log (so the chat shows the skill invocation as a normal
   tool card with the skill body and manifest as the result).
2. Extends the underlying conversation with a synthetic
   `function_call` + `function_call_output` pair, so on the next
   model turn the agent sees the skill body as if *it* had called
   `invoke_skill`. The model then proceeds with whatever the skill
   instructs.

Skills outside the session's agent scope are not listed and not
invocable, even by exact name.

## Scoping

- Leave **Agents** empty on a skill to make it visible to every
  session (global skill).
- Pick one or more agents to restrict the skill to those agents only.
  A `quote_followup` skill that only makes sense for the Sales agent
  can be pinned to it; the read-only Analyst will not see it.
- The visibility filter is applied in both directions: the addendum
  the LLM sees, and the `invoke_skill` permission check.

## Installation

Download the module and add it to your Odoo addons folder. Log into
your Odoo server, open the Apps menu, enable developer mode, click
**Update Apps List**, and install **MuK AI Skills**. Requires
`muk_ai` and `muk_mcp`.

## Upgrade

Download the updated module, replace the folder in your addons path,
restart the server, open the Apps menu, find **MuK AI Skills**, and
click Upgrade.

## Credits

**Contributors**

- Mathias Markl &lt;mathias.markl@mukit.at&gt;

**Author &amp; Maintainer**

This module is maintained by [MuK IT GmbH](https://www.mukit.at/). MuK
IT is an Austrian company specialized in customizing and extending
Odoo. Contact: sale@mukit.at or https://mukit.at.
