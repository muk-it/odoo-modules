================
MuK AI Assistant
================

A complete agentic AI assistant inside Odoo. MuK AI ships a native
OWL chat client, a session-based agent runtime, and three first-class
LLM providers (**OpenAI**, **Anthropic**, **Google Gemini**) with
live token and reasoning streaming. The assistant talks to your data
through the same ``muk_mcp`` tool registry your external AI clients
already use — one source of truth, one permission model, one audit
trail.

Includes human-in-the-loop ``ask_user`` support, a session-scoped
approval gate for risky writes, per-agent tool filters, read-only
scope enforcement, multimodal attachments (images, PDFs, text files),
lazy tool loading with a per-agent essentials list, agent suggestion
prompts, field history versioning, and a prebuilt catalog of current
GPT-5.x / Claude 4.x / Gemini 2.5/3.x models with input/output/cache
pricing.

It is also the foundation for the rest of the MuK AI suite: the
``REGISTRY`` in ``providers/__init__.py`` drives both the in-memory
dispatcher and the stored ``muk_ai.provider`` records, so adding a
new provider is a single-file drop-in, and downstream add-ons plug
extra tools, agents and UI extensions onto the same runtime.

Installation
============

To install this module, you need to:

Download the module and add it to your Odoo addons folder. Afterward,
log on to your Odoo server and go to the Apps menu. Trigger the debug
mode and update the list by clicking on the "Update Apps List" link.
Now install the module by clicking on the install button.

Upgrade
=======

To upgrade this module, you need to:

Download the module and add it to your Odoo addons folder. Restart the
server and log on to your Odoo server. Select the Apps menu and
upgrade the module by clicking on the upgrade button.

Menu layout
===========

Everything lives under **MuK AI** in the app menu:

- **Chat** — the main client action (also reachable at ``/odoo/ai``).
- **Agents** — named presets (system prompt, model, tool filter,
  approval mode, suggestions).
- **Reports** *(system)* — Sessions, Tool Logs, Approval Log.
- **MCP** *(system)* — the underlying tool Registry and Playground
  from ``muk_mcp``.
- **Configuration** *(system)* — Providers, Models.
- **Settings** *(system)* — one-line defaults under the standard
  General Settings page.

Configuration
=============

**Settings — Settings > General Settings > MuK AI**

- **Default Provider** — falls back to the first active provider when
  an agent does not pin one.
- **Default Agent** — used for new chat sessions when the user hasn't
  picked one.

Everything else is configured per-record, not globally.

**Providers — MuK AI > Configuration > Providers**

One record per provider implementation (``openai``, ``anthropic``,
``google``). Fields:

- **API Key** — authentication token for this provider.
- **Default Model** — ``muk_ai.model`` used when an agent does not
  specify one.
- **Max Tokens** — completion-token cap per request (default
  ``4096``).
- **Request Timeout** — HTTP timeout in seconds (default ``60``).
- **Idle Timeout** — seconds without a streamed chunk before the
  stream is aborted and the session is marked errored (default
  ``45``).
- **Rate Limit (per minute)** — max sessions a single user may create
  per minute. ``0`` disables the cap.

A **Test Connection** button on the provider form sends a tiny probe
(``Reply with a single word.``) and reports success or failure without
leaving the page.

**Models — MuK AI > Configuration > Models**

The model catalog ships prefilled with current API-available SKUs
(GPT-5, 5.1, 5.2, 5.4 family + Pro, 5.5, 5.5 Pro; GPT-4.1 family;
GPT-4o; o-series; Claude Opus 4/4.1/4.5/4.6/4.7, Sonnet 4/4.5/4.6,
Haiku 3.5/4.5; Gemini 2.5 Pro/Flash/Flash-Lite/Flash-Image and 3.x
previews). Each record carries:

- **Technical Name** — API id (``gpt-5.4``, ``claude-sonnet-4-6``,
  ``gemini-2.5-flash``, …).
- **Provider** — the parent ``muk_ai.provider``.
- **Context Window** — used for the colour-coded meter in the chat.
- **Input / Cached / Output Rate** — USD per 1M tokens; drives the
  per-session cost display and the usage pivot.

**Access Groups**

- **Internal User** (``base.group_user``) — opens the chat, manages
  their own sessions, reads agents and their suggestions.
- **System** (``base.group_system``) — manages every session, edits
  agents and providers, reviews approvals and tool logs.

Record rules keep each user's sessions private.

Usage
=====

**Chatting**

Open *MuK AI > Chat* (or ``/odoo/ai``). Create a session from the
sidebar, pick an agent (optional), type a message and hit ``Enter``.
The reply streams in live via the Odoo bus; tool calls render as
collapsible cards with live-filling arguments so you can see exactly
what the model is about to run. ``Shift+Enter`` inserts a newline. A
single Send/Stop toggle cancels an in-flight stream.

A systray icon in the top bar surfaces running sessions and lets you
pop out a floating chat window so the assistant stays reachable while
you navigate other views.

**Write-tool safety (session-scoped approvals)**

Risky write calls pause the session and ask before running. An update
to a mail-tracked field, a workflow method like ``action_post`` on an
invoice, a deletion, or a create on a high-impact model triggers an
approval card inline in the chat. The card shows why it fired
("approving because ``state`` is tracked on ``account.move``"), the
proposed JSON arguments, and three buttons:

- **Approve once** — dispatches this call and logs the decision.
- **Allow for Session** — same, plus adds a signature to the session
  so matching calls (same tool, same model, same sensitive fields)
  auto-approve for the rest of *this* session.
- **Reject** — returns a ``rejected_by_user`` tool output so the model
  can recover (clarify, propose a safer alternative).

Every decision is recorded under *MuK AI > Reports > Approval Log*
with the proposed vs. executed arguments. Per-agent **Approval Mode**
lets unattended agents skip the prompt (``Never ask``). Approvals do
not persist across sessions — each new session starts with an empty
allow-list.

**View context**

When the floating chat window is open, the session sticks to the Odoo
view the user is looking at (form record, list, kanban, pivot,
graph). A header pill shows the pinned context (e.g.
``sale.order · SO-00042``) and opens that view on click. Navigation
fired by the agent (``open_record``, ``open_view``, ``open_action``)
updates the pin automatically. The context is injected at request
time as a short ``<ui_ctx>`` tag at the tail of the conversation, so
the model can resolve references like "this order" or "the current
list" without an extra tool call. Type ``/unpin`` to clear it.

**Attachments**

Drop a file onto the composer, paste a screenshot, or click the clip
icon. Images render inline, PDFs and text files show as pills. On
send, every attachment is streamed to the active provider as a native
content block — ``input_image`` / ``input_file`` for OpenAI Responses,
``image`` / ``document`` blocks for Anthropic Messages, inline base64
for Gemini, inline text for small ``.txt`` / ``.csv`` / ``.md`` files.
Accepted types: PNG, JPEG, WebP, GIF, PDF, plain text, CSV, Markdown.
Capped at 128 MiB per file with oversize and unknown-type uploads
rejected server-side. Text files are inlined and truncated past
256 KiB.

**Human-in-the-loop**

When the LLM calls the ``ask_user`` tool, the session pauses in
``waiting`` state and surfaces the question in the chat. Your answer
is fed back as a ``function_call_output`` so the model resumes the
turn exactly where it left off.

**Context-window meter**

The chat header shows a colour-coded pill with the share of the
current model's context window consumed by the last turn's input.
Below 85 % is idle, 85–95 % flags a warning and offers to auto-
compact, 95 %+ triggers auto-compaction silently. Context sizes come
from the ``muk_ai.model`` record for the agent's active model.

**Slash commands**

Start a message with ``/`` to open a pop-up of available commands:

- ``/help`` — inline cheat sheet.
- ``/clear`` — confirm and wipe the current conversation and tool
  log, keeping the session record and agent.
- ``/compact`` — ask the provider for a ≤500-token summary and
  replace the conversation with it, freeing context without losing
  continuity.
- ``/unpin`` — clear the view-context pin.

**Agents**

Open *MuK AI > Agents*. An agent is a named preset:

- **System Prompt** — rendered with inline-template placeholders
  (``{{ user.name }}``, ``{{ company.name }}``, ``{{ today }}``,
  ``{{ approval_mode }}``) at session start and on ``/compact``.
- **Model** — optional override; blank falls back to the provider
  default.
- **Provider-native toggles** — enable the active provider's web
  search, image generation and code interpreter tools when the
  provider supports them.
- **Read-only** — enforced server-side through the MCP scope check,
  not just a prompt instruction.
- **Tool Filter** — whitelist of MCP tool names the agent may call
  (empty = all tools allowed).
- **Essential Tools** — names that ship with full schemas at session
  start. Empty falls back to a sensible default (read-side primitives
  + UI helpers + ``ask_user``) and turns lazy loading on; populate it
  to opt into a custom essentials set, or set it to every catalog name
  to ship the full eager-mode tool array. Names outside the tool
  filter are silently dropped.
- **Approval Mode** — ``Ask on writes`` (default) or ``Never ask`` for
  unattended agents.
- **Suggestions** — starter prompts shown in the empty chat, editable
  as a one2many kanban inside the agent form.

Every system-prompt edit snapshots the prior value into the agent's
``prompt_history`` JSON column (via the reusable
``muk_ai.revision.mixin``). The **Prompt History** stat button
on the agent form opens a side-by-side dialog that lists all prior
revisions with author + timestamp and lets you restore any of them.

Lazy tool loading
=================

Shipping every MCP tool's JSON schema in the ``tools`` array of every
turn is expensive on context. MuK AI lets each agent declare a small
**Essential Tools** set that is loaded eagerly; every other catalog
tool is advertised by name only inside an ``<available_tools>`` block
appended to the system prompt. The model fetches full schemas on
demand through a built-in meta-tool:

- ``tool_load(names=[...])`` — pulls one or more schemas from the
  catalog. The names are appended to the session's
  ``expanded_tool_names`` list and stay loaded for the rest of the
  session.
- ``tool_load(names=[...], call={name, arguments})`` — load *and*
  execute one of the just-loaded tools in the same round-trip; the
  schemas plus the inline tool result come back in a single
  ``function_call_output``, no follow-up turn needed. This is the
  preferred shape for one-shot lookups.

Unknown names come back under an ``unknown`` key so the model can
recover gracefully. ``ask_user`` is auto-injected when approvals are
enabled, regardless of the essentials list. Leaving **Essential
Tools** empty enables the default lazy mode (read-side primitives +
UI helpers + ``ask_user``); populate it to override.

Runtime context block
=====================

Alongside the agent's system prompt and ``<available_tools>`` list,
each session injects a short ``<runtime>`` block stating the current
Odoo version, today's date, the user (id, timezone), the company
(id), the active approval mode, and — when relevant — the list of
companies the user can access (with a hint to pass
``allowed_company_ids`` for cross-company searches). This means the
model never has to spend a turn calling ``whoami`` or ``today`` to
ground its first reply.

Providers
=========

The provider layer is a Python registry (``providers/__init__.py``)
plus stored configuration records (``muk_ai.provider``). Each provider
class declares ``name / label / default_model / default_url /
supports_*``, implements ``headers()`` and ``request()``, and inherits
shared HTTP + SSE streaming plumbing from ``ProviderBase``.

+---------------+-----------+---------------------------------------------------------------------------+
| Provider      | Streaming | Notes                                                                     |
+===============+===========+===========================================================================+
| ``openai``    | SSE       | OpenAI Responses API; skips ``temperature`` for reasoning models          |
+---------------+-----------+---------------------------------------------------------------------------+
| ``anthropic`` | SSE       | Messages API; in-dispatcher adapter for ``tool_use`` / ``tool_result``    |
+---------------+-----------+---------------------------------------------------------------------------+
| ``google``    | SSE       | Gemini ``streamGenerateContent``; native image generation and grounding   |
+---------------+-----------+---------------------------------------------------------------------------+

All three providers emit the same on-delta events (``text``,
``tool_start``, ``tool_args``), so the chat UI feels identical
regardless of which provider is active.

Tool Dispatch via muk_mcp
=========================

Agents call exactly the same tool surface as your external MCP
clients — no duplicate catalog, no divergence. The MuK AI agent pulls
tools from ``muk_mcp`` filtered by the ``odoo`` registry, and a
handful of UI-specific tools are registered there for the in-Odoo
agent only:

- ``open_record`` — navigate the user to a specific record.
- ``open_view`` — open a filtered list/kanban/pivot view of a model.
- ``open_action`` — launch an existing Odoo action by xmlid or id
  (honouring the action's ``groups_id``).
- ``show_notification`` — toast a message in the Odoo web client.
- ``ask_user`` — pause the session for clarification.

The chat UI auto-dispatches any returned ``ir.actions.*`` descriptor,
so the model can navigate the user through the UI as part of a reply.

Extending the Provider Set
==========================

Create a new addon (do not modify ``muk_ai``). Subclass
``ProviderBase`` in your addon:

.. code-block:: python

    # muk_ai_mistral/providers/mistral.py
    from odoo.addons.muk_ai.providers.base import ProviderBase


    class MistralProvider(ProviderBase):
        name = 'mistral'
        label = "Mistral"
        default_model = 'mistral-large-latest'
        default_url = 'https://api.mistral.ai/v1'

        def headers(self):
            return {
                'Authorization': f'Bearer {self.api_key}',
                'Content-Type': 'application/json',
            }

        def request(
            self,
            inputs,
            tools_schema=None,
            text_schema=None,
            on_delta=None,
            model=None,
            enable_web_search=False,
            enable_image_generation=False,
            enable_code_interpreter=False,
            extra=None,
        ):
            ...

Register it by mutating the imported ``REGISTRY`` from your addon's
``__init__.py`` chain (runs at import time, before any session needs
it):

.. code-block:: python

    # muk_ai_mistral/providers/__init__.py
    from odoo.addons.muk_ai.providers import REGISTRY

    from .mistral import MistralProvider

    REGISTRY[MistralProvider.name] = MistralProvider

Add ``<record id="provider_mistral" model="muk_ai.provider">`` to
``data/provider.xml`` and matching ``muk_ai.model`` seeds in
``data/model.xml``. Depend on ``muk_ai`` in your ``__manifest__.py``.
Selection, default-model lookup, capability probes, and dispatch all
pick it up automatically.

Extending the Tool Set
======================

Agents inherit every tool registered via the ``muk_mcp`` pattern (see
``muk_mcp``'s index for the full guide). To scope a tool to the
in-Odoo agent only, set the decorator's ``registry='odoo'``; external
MCP clients keep seeing the default ``mcp`` surface only.

Security & Audit
================

Every session carries a JSON-serialised tool log covering user
messages, tool calls, tool results, assistant text, ``ask_user``
prompts, and answers. Combined with ``muk_mcp``'s own audit log,
every AI-driven read or write on your data is traceable end-to-end.

The per-provider idle watchdog aborts dead connections. Runaway loops
are capped by ``MAX_ITERATIONS = 20`` per turn and
``MAX_TOOL_CALLS_PER_ROUND = 10``; an ``ask_user``-at-cap edge is
handled gracefully so resumed sessions do not get stuck.

Sessions inherit ``bus.listener.mixin`` and route streaming events
through the owner's partner channel — not a guessable string — so one
user cannot eavesdrop on another.

Credits
=======

Contributors
------------

* Mathias Markl <mathias.markl@mukit.at>
* Kerrim Abd E-Hamed <kerrim.adbelhamed@mukit.at>

Author & Maintainer
-------------------

This module is maintained by the `MuK IT GmbH <https://www.mukit.at/>`_.

MuK IT is an Austrian company specialized in customizing and extending
Odoo. We develop custom solutions for your individual needs to help you
focus on your strength and expertise to grow your business.

If you want to get in touch please contact us via mail
(sale@mukit.at) or visit our website (https://mukit.at).
