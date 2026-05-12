=========================
MuK AI Enterprise Bridge
=========================

One-way bridge so MuK AI sessions can borrow Odoo Enterprise AI
building blocks. **MuK AI Enterprise Bridge** lets a ``muk_ai.agent``
opt-in to two Enterprise primitives — ``ai.topic`` server-action
tools and ``ai.agent.source`` RAG sources — and automatically threads
each record's ``Model._ai_initialise_context`` output into the MuK AI
chat's view context. The Enterprise side is never modified: the
Discuss ``ai_chat`` channels, the systray / chatter / composer
buttons, the ``ai.agent`` replies, ``LLMApiService``, the
``ai_fields`` cron and every optional ``ai_*`` satellite keep their
existing behaviour. Both chat clients coexist; the user picks which
one to open.

Borrowed Enterprise tools surface inside MuK AI sessions as MCP tools
named ``ee_action_<xmlid_name>``, going through the same approval
gate and audit log as native MuK AI tools. RAG snippets are appended
to the rendered system prompt inside a ``<rag>...</rag>`` block, and
the per-record Enterprise context appears inside
``<ee_ctx>...</ee_ctx>``. Empty defaults mean nothing changes for
agents that haven't been explicitly configured.

This is a pure additive bridge on top of ``muk_ai`` and ``ai``: no
provider routing, no chat takeover, no JS launcher patch, no
``_inherit`` on Enterprise models. Just one Python adapter and two
M2M fields on the MuK AI agent.

Installation
============

To install this module, you need to:

Download the module and add it to your Odoo addons folder. Afterward,
log on to your Odoo server and go to the Apps menu. Trigger the debug
mode and update the list by clicking on the "Update Apps List" link.
Now install the module by clicking on the install button. Requires
``muk_ai``, Enterprise ``ai``, and a PostgreSQL server with the
``pgvector`` extension if you want RAG borrowing to work.

Upgrade
=======

To upgrade this module, you need to:

Download the module and add it to your Odoo addons folder. Restart
the server and log on to your Odoo server. Select the Apps menu and
upgrade the module by clicking on the upgrade button.

What's in the box
=================

- **muk_ai.agent extension** — two Many2many fields,
  ``ee_topic_ids`` (→ ``ai.topic``) for tool borrowing and
  ``ee_source_ids`` (→ ``ai.agent.source``) for RAG borrowing, plus
  an *Enterprise* notebook page on the agent form to pick them.
- **muk_ai.session extension** — appends a ``<rag>`` block to the
  rendered system prompt when the agent has ``ee_source_ids`` set
  and the latest user message can be embedded, and an ``<ee_ctx>``
  block when the session's ``view_context`` pins a record. Both are
  no-ops when their inputs are empty.
- **muk_mcp.tool extension** — when a MuK AI session is running for
  an agent that has ``ee_topic_ids`` set, the bridge injects each
  borrowed Enterprise server action into ``get_tools()`` as
  ``ee_action_<xmlid_name>`` and dispatches ``_call``\\ s with that
  prefix through Enterprise's ``_ai_tool_run``.
- **muk_ai_enterprise.ee_tools adapter** — abstract model that
  resolves a tool name back to its ``ir.actions.server`` record,
  enforces the ``use_in_ai`` filter, coerces the action's JSON
  schema into the MCP shape, runs the action against the session's
  pinned record (or the calling user as a fallback), and serialises
  the result back through the standard ``muk_mcp.log`` audit trail.

Configuration
=============

1. Install **MuK AI Enterprise Bridge**. It pulls in ``muk_ai`` and
   ``ai`` automatically.
2. Open *MuK AI > Agents* and edit a MuK AI agent.
3. On the new **Enterprise** notebook page, pick the topics whose
   server-action tools you want exposed (``EE Topics (borrow tools)``)
   and the RAG sources you want injected (``EE RAG Sources``). Both
   fields default to empty; selecting nothing opts out.
4. Optional: open a record that has a non-trivial
   ``_ai_initialise_context`` override and open the MuK AI chat on
   it — the per-record context flows into the prompt automatically,
   no per-agent setting needed.

Tool borrowing
==============

Every action in the picked topics that has ``use_in_ai=True`` is
exposed as a single MCP tool named ``ee_action_<xmlid_name>``. The
description, JSON schema and category are read straight from the
Enterprise record, so you configure the action once in *AI >
Configuration > Topics* and both surfaces (Enterprise chat and MuK
AI chat) see the same tool.

Dispatch routes through Enterprise's
``ir.actions.server._ai_tool_run`` under the calling user's
environment, so Enterprise's access checks and audit hooks all run
unchanged. The MuK AI session's ``muk_mcp.log`` records the call
exactly like it would for a native MCP tool — including arguments,
response, status and timing.

When the MuK AI agent has ``read_only=True``, ``ee_action_*`` tools
are filtered out of the schema entirely and any direct dispatch
raises a ``UserError``, so a read-only agent can never mutate
through borrowed Enterprise tools.

The action runs against the record pinned in the session's
``view_context`` (``kind='record'``). For sessions without a pinned
record, the calling user is used as the fallback record so actions
that don't care about a record target keep working unchanged.

RAG borrowing
=============

On every user message, the bridge embeds the latest user text via
``LLMApiService.get_embedding(...)``, queries
``ai.embedding._get_similar_chunks(...)`` against the agent's
``ee_source_ids``, and appends the top hits to the rendered system
prompt inside a ``<rag>...</rag>`` block. The embedding model and
dimensions are read from Enterprise
(``ai.agent._get_embedding_model`` and
``ai.embedding._get_dimensions``), so changes on the Enterprise side
flow through immediately.

When the source-set is empty, the user message is empty, embeddings
fail, or ``pgvector`` is missing, the ``<rag>`` block is silently
skipped — never injected as a half-empty placeholder.

Per-record context
==================

When the MuK AI chat opens on a record, the session's
``view_context`` ends up with ``kind='record'`` plus the model and
id. The bridge intercepts that, calls
``record._ai_initialise_context('mail_composer', None, None)`` (the
same hook Enterprise uses for its mail composer flow, which returns
the record's serialised field values plus any model-specific
augmentation) and stores the result in
``view_context.ee_init_context``. The system prompt rendering then
appends it inside an ``<ee_ctx>...</ee_ctx>`` block.

Models without an ``_ai_initialise_context`` override fall through
silently. Records inheriting ``mail.thread`` get the chatter
history mixed in for free, courtesy of Enterprise's existing
``mail.thread._ai_initialise_context`` override.

Coexistence
===========

The bridge depends hard on ``muk_ai`` and ``ai`` but on no other
Enterprise ``ai_*`` satellite. Optional satellites —
``ai_documents``, ``ai_livechat``, ``ai_fields``,
``ai_server_actions``, ``ai_knowledge``, ``ai_website``, ``ai_crm``,
etc. — simply contribute more ``ai.topic`` and ``ai.agent.source``
records that admins can then pick from the new *Enterprise* notebook
page. Nothing else needs to change.

Uninstalling a satellite cleans up its M2M references through
Odoo's default ``ondelete`` behaviour, so a MuK AI agent that used
to borrow ``ai_crm.topic_create_lead`` simply stops seeing
``ee_action_topic_create_lead`` after ``ai_crm`` is uninstalled — no
crash, no orphaned tool entry.

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
