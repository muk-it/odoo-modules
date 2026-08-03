=============
MuK AI Skills
=============

Pre-built agent skills your users (or the LLM itself) can switch into.
A **skill** is a DB-backed record bundling a name, a one-line
description for LLM discovery, a markdown body of instructions, and
optional file attachments. Visible skills are listed in a
system-prompt addendum so the agent can pick one autonomously, and
users can invoke them from the skills panel in the chat composer or
with a ``/<name>`` slash command.

This addon plugs into ``muk_ai``'s session runtime via ``_inherit``
only — no fork of ``muk_ai`` or ``muk_mcp`` source.

Installation
============

To install this module, you need to:

Download the module and add it to your Odoo addons folder. Afterward,
log on to your Odoo server and go to the Apps menu. Trigger the debug
mode and update the list by clicking on the "Update Apps List" link.
Now install the module by clicking on the install button. Requires
``muk_ai`` and ``muk_mcp``.

Upgrade
=======

To upgrade this module, you need to:

Download the module and add it to your Odoo addons folder. Restart the
server and log on to your Odoo server. Select the Apps menu and
upgrade the module by clicking on the upgrade button.

What's in the box
=================

- **muk_ai.skill model** — name, label, description, markdown body,
  attached resources (``ir.attachment``), agent scoping (specific
  agents or global), prompt revision history via the reusable
  ``muk_ai.revision.mixin`` from ``muk_ai``.
- **invoke_skill MCP tool** — agent-callable, returns the skill body
  plus a resource manifest with ``uri`` entries the agent can fetch
  via ``muk_mcp``'s generic ``read_resource``.
- **System-prompt addendum** — every visible skill is listed by
  technical name + one-line description inside an
  ``<available_skills>`` block appended to the agent's system prompt.
- **Slash command in chat** — typing ``/<skill_name>`` in the composer
  fires the skill directly, mirroring the same ``invoke_skill`` flow
  the LLM uses but without an LLM round-trip.
- **Manage menu link** — *MuK AI > Skills* (and ``/odoo/ai-skills``).

Building a skill
================

Open *MuK AI > Skills* and create a record:

- **Technical Name** — lowercase identifier matching
  ``[a-z][a-z0-9_]*``, used for the ``/name`` slash command and in
  the LLM-facing addendum (e.g. ``quote_followup``, ``lead_brief``,
  ``summarize_thread``).
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
  with a stable ``odoo://attachment/<id>`` URI; the agent fetches the
  bytes by passing that URI to ``read_resource``.
- **Agents** — leave empty to make the skill global, or pick one or
  more agents to scope visibility. Sessions only see skills whose
  agent scope matches (or skills with no scope).
- **Active / Sequence** — standard Odoo flags; sequence drives the
  order in the addendum and the slash-command popover.

Body edits snapshot the prior value into the skill's
``prompt_history`` JSON column. The **History** stat button on the
skill form opens a side-by-side dialog listing every prior revision
with author and timestamp; restoring rolls back to that revision.

Agent invocation
================

When a session starts, ``muk_ai_skills`` walks the visible-skill set
for the session's agent and appends an ``<available_skills>`` block
to the system prompt. If the agent calls
``invoke_skill(skill_name='quote_followup')``, the tool returns:

.. code-block:: json

    {
      "name": "quote_followup",
      "label": "Quote Follow-up",
      "body": "## Steps\n1. Look up the sale.order by ref or domain…",
      "resources": [
        {
          "name": "tone_guide.md",
          "uri": "odoo://attachment/42",
          "mimetype": "text/markdown"
        }
      ]
    }

The agent treats the body as fresh instructions and reads any of the
listed resources via ``read_resource(uri='odoo://attachment/42')`` —
no new tool needed for that, the URI handler is in ``muk_mcp``.

User invocation
===============

Click the bolt next to the paperclip to open the skills panel. It
lists the skills visible to the session as cards, groups the ones you
ran last under *Recently used*, and carries its own search field, so
the composer keeps whatever you were writing. Arrow keys move the
selection, Enter runs it, Escape closes the panel and hands the caret
back to the composer. On a touch device nothing is auto-focused, so
the on-screen keyboard stays down until you tap the search field.

Type ``/`` in the composer to open the slash-command popover.
Built-in commands (``/help``, ``/clear``, ``/compact``, ``/unpin``)
are merged with the visible skills for the session. Picking
``/quote_followup`` (or typing it and hitting Enter) calls
``invoke_skill_from_chat`` on the session, which:

1. Records a ``tool_call`` and matching ``tool_result`` in the
   session event log (so the chat shows the skill invocation as a
   normal tool card with the skill body and manifest as the result).
2. Extends the underlying conversation with a synthetic
   ``function_call`` + ``function_call_output`` pair, so on the next
   model turn the agent sees the skill body as if *it* had called
   ``invoke_skill``. The model then proceeds with whatever the skill
   instructs.

Skills outside the session's agent scope are not listed and not
invocable, even by exact name.

Scoping
=======

- Leave **Agents** empty on a skill to make it visible to every
  session (global skill).
- Pick one or more agents to restrict the skill to those agents only.
  A session with no ``agent_id`` only sees global skills.
- The visibility filter is applied in both directions: the addendum
  the LLM sees, and the ``invoke_skill`` permission check.

Credits
=======

Contributors
------------

* Mathias Markl <mathias.markl@mukit.at>

Author & Maintainer
-------------------

This module is maintained by the `MuK IT GmbH <https://www.mukit.at/>`_.

MuK IT is an Austrian company specialized in customizing and extending
Odoo. We develop custom solutions for your individual needs to help
you focus on your strength and expertise to grow your business.

If you want to get in touch please contact us via mail
(sale@mukit.at) or visit our website (https://mukit.at).
