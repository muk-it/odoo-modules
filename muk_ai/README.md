# MuK AI Assistant

A complete agentic AI assistant inside Odoo. MuK AI ships a native
OWL chat client, a session-based agent runtime, and three first-class
LLM providers (**OpenAI**, **Anthropic**, **Google Gemini**) with
live token and reasoning streaming. The assistant talks to your data
through the same `muk_mcp` tool registry your external AI clients
already use — one source of truth, one permission model, one audit
trail.

Includes human-in-the-loop `ask_user` support, a session-scoped
approval gate for risky writes, per-agent tool filters, read-only
scope enforcement, multimodal attachments (images, PDFs, text files),
lazy tool loading with a per-agent essentials list, agent suggestion
prompts, field history versioning, and a prebuilt catalog of current
GPT-5.x / Claude 4.x–5 / Gemini 2.5–3.x models with input, output and
cache (read + write) pricing and per-model reasoning-effort tiers.

It is also the foundation for the rest of the MuK AI suite: the
`REGISTRY` in `providers/__init__.py` drives both the in-memory
dispatcher and the stored `muk_ai.provider` records, so adding a new
provider is a single-file drop-in, and downstream add-ons plug extra
tools, agents and UI extensions onto the same runtime.

## Menu layout

Everything lives under **MuK AI** in the app menu:

- **Chat** — the main client action (also reachable at `/odoo/ai`)
- **Agents** — named presets (system prompt, model, tool filter,
  approval mode, suggestions)
- **Reports** *(system)* — Sessions, Tool Logs, Approval Log
- **MCP** *(system)* — the underlying tool Registry and Playground
  from `muk_mcp`
- **Configuration** *(system)* — Providers, Models, Spaces
- **Settings** *(system)* — one-line defaults under the standard
  General Settings page

## Configuration

**Settings — `Settings > General Settings > MuK AI`**

- **Default Provider** — falls back to the first active provider when
  an agent does not pin one.
- **Default Agent** — used for new chat sessions when the user hasn't
  picked one.
- **Iteration Limit** — max tool-calling rounds per worker slice
  (default `20`); the model is warned shortly before it so it can wrap
  up.
- **Turn Runtime** — wall-clock budget for a whole user turn across all
  slices (default `3600 s`); exceeding it stops the turn with an error.
- **Slice Runtime** — wall-clock budget for one worker slice (default
  `600 s`); a slice that exceeds it is checkpointed and resumed by a
  fresh worker on the next cron tick.
- **Cost Limit** — maximum spend per user turn in the model's price
  currency (`0` disables).

The same page lists the installable **MuK AI extensions** (MCP,
Compatible Providers, Mistral, Schedule, Skills, Voice, Workflows) as
one-click toggles.

Everything else is configured per-record, not globally:

**Providers — `MuK AI > Configuration > Providers`**

One record per provider implementation (`openai`, `anthropic`,
`google`). Fields:

- **API Key** — authentication token for this provider.
- **Default Model** — `muk_ai.model` used when an agent does not
  specify one.
- **Max Tokens** — completion-token cap per request (default `4096`).
- **Request Timeout** — HTTP timeout in seconds (default `60`).
- **Idle Timeout** — seconds without a streamed chunk before the
  stream is aborted and the session is marked errored (default `45`).
- **Rate Limit (per minute)** — max sessions a single user may create
  per minute. `0` disables the cap.

A **Test Connection** button on the provider form sends a tiny probe
(`Reply with a single word.`) and reports success or failure without
leaving the page.

**Models — `MuK AI > Configuration > Models`**

The model catalog ships prefilled with current API-available SKUs — the
GPT-5.x family (5, 5.1, 5.2, 5.4 + Pro, 5.5 + Pro, and the 5.6 Sol / Terra
/ Luna tiers), GPT-4.1 family, GPT-4o and the o-series; Claude (Opus 4.x
through 4.8, Sonnet 4.x and Sonnet 5, Haiku, Fable 5); and Gemini (2.5
Pro/Flash/Flash-Lite/Flash-Image plus the 3.x previews). Each record
carries:

- **Technical Name** — API id (`gpt-5.2`, `claude-sonnet-5`,
  `gemini-3.5-flash`, …).
- **Provider** — the parent `muk_ai.provider`.
- **Context Window** — used for the colour-coded meter in the chat.
- **Input / Output Rate** and **Cache Read / Cache Write Rate** — USD per
  1M tokens. Input is split into fresh, cache-read and cache-write tokens
  so prompt-cached turns are billed at their real (much lower) cost; the
  rates drive the per-session cost display and the usage pivot.
- **Supported Reasoning Efforts** / **Default Reasoning Effort** — the
  thinking tiers this model accepts (see *Reasoning effort* under Agents);
  models without a thinking knob leave these empty.

**Access Groups**

- **Internal User** (`base.group_user`) — opens the chat, manages
  their own sessions, reads agents and their suggestions.
- **System** (`base.group_system`) — manages every session, edits
  agents and providers, reviews approvals and tool logs.

Record rules keep each user's sessions private.

## Usage

**Chatting**

Open **MuK AI > Chat** (or `/odoo/ai`). Create a session from the
sidebar, pick an agent (optional), type a message and hit `Enter`.
The reply streams in live via the Odoo bus; tool calls render as
collapsible cards with live-filling arguments so you can see exactly
what the model is about to run. `Shift+Enter` inserts a newline. A
single Send/Stop toggle cancels an in-flight stream.

A systray icon in the top bar surfaces running sessions and lets you
pop out a floating chat window so the assistant stays reachable while
you navigate other views.

**Spaces**

Chats pile up fast, so the sidebar groups them into **spaces**. Create
one with the `+` next to *Spaces*, drag chats into it to file them and
drag them out to loosen them again, and drag a space by its grip to
reorder the list. The pencil opens an editor for the space name, its
Font Awesome icon (searchable grid) and an optional **default agent**
preselected for every chat started inside it — the `+` on a space row
starts such a chat. Unread chats are counted per space; click the badge
to narrow that space to its unread conversations. Every branch
paginates on its own, so opening a space with hundreds of chats costs
one page.

Modules can ship **system spaces** whose membership comes from a stored
domain instead of manual filing — `muk_ai_schedule` ships a *Scheduled*
space collecting every chat a schedule started. They belong to nobody,
are visible to everyone, and cannot be renamed, reordered or dropped
into; one record serves the whole database, so nothing is duplicated
per user and matching chats appear retroactively. Administrators manage
every space under **MuK AI > Configuration > Spaces**.

**Source citations**

When the assistant reads data to answer, what it relied on is
collected as *sources* and shown as a chip under the reply. Expand it
to see each source — an Odoo record (with its model and a one-click
link that opens it) or, when the agent used `web_fetch`, the external
web page it read. The same list is mirrored in the *Artifacts* side
rail, so every figure is traceable to its origin.

**Tool groups**

When a turn fires several tool calls back to back, they collapse into
a single *Used N tools* card instead of stacking many. The header
shows the tool-name chips and aggregate status — a green check with
the success count and a red × with the error count — and expands to
reveal each individual call. Each card fills its arguments live as the
model streams them and then drops in the result in place, so you watch
the work happen without waiting for the whole turn to finish.

**Rewind, branch & regenerate**

Hover any message for its actions. **Rewind** removes that message and
everything after it (after a confirmation that names how many events
drop). **Branch** forks the conversation into a brand-new session
seeded with the history up to that point, leaving the original intact.
**Regenerate**, offered on the last answer, re-runs the turn. Rewind
and Branch are disabled while a reply is streaming and on messages
already folded into compacted history.

**Artifacts panel**

A collapsible **Artifacts** rail (paperclip icon in the header)
gathers everything a conversation produced. An *Attachments* tab lists
every uploaded file and every AI-**generated image** as a card you can
open full-size in Odoo's file viewer; a *Sources* tab lists the cited
records and web pages. Tabs appear only when they have content.

**In-chat search**

The search icon opens a find-in-conversation bar. Matches across user
and assistant text are highlighted with a current/total counter;
`Enter` / `Shift+Enter` jump to the next / previous hit and scroll it
into view, `Esc` closes.

**Notifications**

Sessions that finish or need you while you are elsewhere signal you.
The MuK AI systray icon carries a live running dot whenever a session
is running or waiting, plus a red count of sessions awaiting your
attention; unread sessions are marked and sorted to the top in both
the systray dropdown and the chat sidebar. Users on the *inbox*
notification preference also get completion notices as web push and
Enterprise mobile (OCN) push. Opening the session clears the flag.

**Write-tool safety (session-scoped approvals)**

Risky write calls pause the session and ask before running. An update
to a mail-tracked field, a workflow method like `action_post` on an
invoice, a deletion, or a create on a high-impact model triggers an
approval card inline in the chat. The card shows why it fired
("approving because `state` is tracked on `account.move`"), the
proposed JSON arguments, and three buttons:

- **Approve once** — dispatches this call and logs the decision.
- **Allow for Session** — same, plus adds a signature to the session
  so matching calls (same tool, same model, same sensitive fields)
  auto-approve for the rest of *this* session.
- **Reject** — returns a `rejected_by_user` tool output so the model
  can recover (clarify, propose a safer alternative).

Every decision is recorded under **MuK AI > Reports > Approval Log**
with the proposed vs. executed arguments. Per-agent **Approval Mode**
lets unattended agents skip the prompt (`Never ask`). Approvals do
not persist across sessions — each new session starts with an empty
allow-list.

**View context**

When the floating chat window is open, the session sticks to the
Odoo view the user is looking at (form record, list, kanban, pivot,
graph). A header pill shows the pinned context (e.g.
`sale.order · SO-00042`) and opens that view on click. Navigation
fired by the agent (`open_record`, `open_view`, `open_action`) updates
the pin automatically. The context is injected at request time as a
short `<ui_ctx>` tag at the tail of the conversation, so the model
can resolve references like "this order" or "the current list"
without an extra tool call. Type `/unpin` to clear it.

**Reshape views from chat**

Ask the assistant to change the list, kanban, pivot or graph you are
looking at — *"group these orders by salesperson"*, *"only show
drafts"*, *"switch to a bar chart"* — and it reshapes that view **in
place** rather than opening a new one. The `adjust_search` tool is a
*client tool*: instead of running on the server it runs in your
browser tab and drives the live search view — activating filters and
group-bys (with `date_order:month`-style intervals), applying field
searches and custom-domain facets, removing facets, switching view
type, and setting pivot/graph measures, chart mode, ordering, stacking
and cumulation. It reports back exactly what it changed, and the
available filter/group-by names when you ask for one it doesn't
recognise.

**Attachments**

Drop a file onto the composer, paste a screenshot, or click the clip
icon. Images render inline, PDFs and text files show as pills. On
send, every attachment is streamed to the active provider as a native
content block — `input_image` / `input_file` for OpenAI Responses,
`image` / `document` blocks for Anthropic Messages, inline base64 for
Gemini, inline text for small `.txt` / `.csv` / `.md` files. Accepted
types: PNG, JPEG, WebP, GIF, PDF, plain text, CSV, Markdown. Capped
at 128 MiB per file with oversize and unknown-type uploads rejected
server-side. Text files are inlined and truncated past 256 KiB.

**Human-in-the-loop**

When the LLM calls the `ask_user` tool, the session pauses in
`waiting` state and surfaces the question in the chat. Your answer is
fed back as a `function_call_output` so the model resumes the turn
exactly where it left off.

**Context-window meter**

The chat header shows a colour-coded pill with the share of the
current model's context window consumed by the last turn's input.
Below 85 % is idle, 85–95 % flags a warning and offers to auto-
compact, 95 %+ triggers auto-compaction silently. Context sizes come
from the `muk_ai.model` record for the agent's active model.

**Slash commands**

Start a message with `/` to open a pop-up of available commands:

- `/help` — inline cheat sheet
- `/clear` — reset the LLM's context for this session. The visible chat
  history stays on screen above a divider; the model loses memory of
  prior turns. Session record and agent are untouched.
- `/compact` — ask the provider for a ≤500-token summary and replace
  the conversation with it, freeing context without losing continuity
- `/unpin` — clear the view-context pin
- `/agent` — switch the active agent for this session
- `/handover` — transfer this chat to another user

**Agents**

Open **MuK AI > Agents**. An agent is a named preset:

- **System Prompt** — rendered with inline-template placeholders
  (`{{ user.name }}`, `{{ company.name }}`, `{{ today }}`,
  `{{ approval_mode }}`) at session start and on `/compact`.
- **Model** — optional override; blank falls back to the provider
  default.
- **Reasoning Effort** — how hard the model thinks before answering:
  `Minimal`, `Low`, `Medium`, `High`, `Extra High` or `Maximum`. Blank
  uses the model's default. Only the tiers the model actually supports
  are offered, and the field disappears entirely for models without a
  thinking knob (Gemini Flash, GPT-4 family, …). If a requested tier is
  above what the model allows it is clamped to the nearest supported
  one, and a provider that still rejects it is retried without the
  effort so the answer is always served.
- **Provider-native toggles** — enable the active provider's web
  search, image generation and code interpreter tools when the
  provider supports them.
- **Read-only** — enforced server-side through the MCP scope check,
  not just a prompt instruction.
- **Tool Filter** — whitelist of MCP tool names the agent may call
  (empty = all tools allowed).
- **Essential Tools** — names that ship with full schemas at session
  start. Empty falls back to a sensible default (read-side primitives
  + UI helpers + `ask_user`) and turns lazy loading on; populate it
  to opt into a custom essentials set, or set it to every catalog
  name to ship the full eager-mode tool array. Names outside the tool
  filter are silently dropped.
- **Approval Mode** — `Ask on writes` (default) or `Never ask` for
  unattended agents.
- **Allow Handoff** — expose this agent as a delegation target so the
  Router (and other agents) can hand a conversation to it mid-session
  (see *Agent handoff* below).
- **Suggestions** — starter prompts shown in the empty chat, editable
  as a one2many kanban inside the agent form.

Every system-prompt edit snapshots the prior value into the agent's
`prompt_history` JSON column (via the reusable
`muk_ai.revision.mixin`). The **Prompt History** stat button on
the agent form opens a side-by-side dialog that lists all prior
revisions with author + timestamp and lets you restore any of them.

**Agent handoff (Router)**

A single chat can be served by more than one agent. Turn on **Allow
Handoff** to make an agent a delegation target; the built-in **Router**
agent then reads the opening request, calls `list_agents`, and hands
the conversation to the best specialist with `switch_agent`. From the
next turn that agent's prompt, tools and model take over the *same*
session, and a specialist can hand back or across later on its own. The
switch is recorded inline in the transcript as an `A → B` marker. Use
`/agent` to switch the active agent yourself at any time.

**Session handover**

Hand a live chat to a colleague. The share icon in the chat header (or
`/handover`) opens a user picker — each internal user shown with
avatar, name and email, searchable — and reassigns the session to them.
The recipient gets the session marked unread, an inbox notification
("… handed you the chat") and a systray badge. Only the session owner
or an administrator can hand over, and not while the session is
running.

**Tool vision**

Tools that return images — a screenshot grabber, a chart generator —
feed those images straight back to the model when the active provider
supports vision (the images are stored on the session and re-sent as a
follow-up turn). Providers without vision get a note that images were
produced but cannot be shown, so the turn still completes cleanly.

## Lazy tool loading

Shipping every MCP tool's JSON schema in the `tools` array of every
turn is expensive on context. MuK AI lets each agent declare a small
**Essential Tools** set that is loaded eagerly; every other catalog
tool is advertised by name only inside an `<available_tools>` block
appended to the system prompt. The model fetches full schemas on
demand through a built-in meta-tool:

- `tool_load(names=[...])` — pulls one or more schemas from the
  catalog. The names are appended to the session's
  `expanded_tool_names` list and stay loaded for the rest of the
  session.
- `tool_load(names=[...], call={name, arguments})` — load *and*
  execute one of the just-loaded tools in the same round-trip; the
  schemas plus the inline tool result come back in a single
  `function_call_output`, no follow-up turn needed. This is the
  preferred shape for one-shot lookups. The inline call passes through
  the same write-approval gate as any other call — a risky write pauses
  for approval instead of running.

Names are resolved tolerating a namespace prefix (`functions.foo` →
`foo`). A load with some misses succeeds and returns the misses under
an `unknown` key so the model can recover; a load where *every* name is
unknown comes back as an explicit error telling the model to use exact
`<available_tools>` names. `ask_user` is auto-injected when approvals
are enabled, regardless of the essentials list. Leaving **Essential
Tools** empty enables the default lazy mode (read-side primitives +
UI helpers + `ask_user`); populate it to override.

## Runtime context block

Alongside the agent's system prompt and `<available_tools>` list,
each session injects a short `<runtime>` block stating the current
Odoo version, today's date, the user (id, timezone), the company
(id), the active approval mode, and — when relevant — the list of
companies the user can access (with a hint to pass
`allowed_company_ids` for cross-company searches). This means the
model never has to spend a turn calling `whoami` or `today` to
ground its first reply.

## Providers

The provider layer is a Python registry (`providers/__init__.py`)
plus stored configuration records (`muk_ai.provider`). Each provider
class declares `name / label / default_model / default_url / supports_*`,
implements `headers()` and `request()`, and inherits shared HTTP + SSE
streaming plumbing from `ProviderBase`. A client is constructed from
the provider *record* itself — API key, timeouts, max tokens,
environment and default model are all read off the record — so there
is one source of truth and no config drift.

| Provider      | Streaming | Notes                                                                         |
|---------------|-----------|-------------------------------------------------------------------------------|
| `openai`      | SSE       | OpenAI Responses API; skips `temperature` for reasoning models                |
| `anthropic`   | SSE       | Messages API; in-dispatcher adapter for `tool_use` / `tool_result`            |
| `google`      | SSE       | Gemini `streamGenerateContent`; native image generation and grounding support |

All three providers emit the same on-delta events (`text`,
`tool_start`, `tool_args`), so the chat UI feels identical regardless
of which provider is active.

**Performance.** Long conversations exploit provider **prompt
caching** — Anthropic `cache_control` breakpoints on the stable prompt
prefix (system block, tools, and a conversation anchor placed before
the per-round volatile trailers) and OpenAI's `prompt_cache_key` keyed
on the session — so the reused prefix is billed at the much cheaper
cache-read rate instead of full price each round. Outbound calls run
over a **pooled keep-alive connection** shared across rounds (with
connect-only retry, so a tool-calling POST is never replayed), cutting
per-round latency. Requested reasoning effort is clamped to each
model's supported tiers, with a transparent retry-without-effort
backstop if a provider still refuses.

## Tool Dispatch via muk_mcp

Agents call exactly the same tool surface as your external MCP
clients — no duplicate catalog, no divergence. The MuK AI agent pulls
tools from `muk_mcp` filtered by the `odoo` registry, and a handful
of UI-specific tools are registered there for the in-Odoo agent only:

- `open_record` — navigate the user to a specific record.
- `open_view` — open a filtered list/kanban/pivot view of a model.
- `open_action` — launch an existing Odoo action by xmlid or id
  (honouring the action's `groups_id`).
- `show_notification` — toast a message in the Odoo web client.
- `ask_user` — pause the session for clarification.
- `adjust_search` — reshape the list/kanban/pivot/graph the user is
  currently looking at (see *Reshape views from chat*). This is a
  *client tool*: it runs in the user's browser tab rather than on the
  server, and only the tab holding the chat answers.
- `web_fetch` — fetch a public web page and return its main content as
  clean Markdown (boilerplate stripped, links and headings kept), or as
  plain text / raw HTML for JSON endpoints. Long pages paginate; `http`
  is upgraded to `https` and an SSRF guard re-validates every redirect
  so only publicly-routable hosts are reached. The fetched page is
  added to the reply's Sources as a citable web link — pair it with the
  provider's native web search to find pages, then read them.

The chat UI auto-dispatches any returned `ir.actions.*` descriptor,
so the model can navigate the user through the UI as part of a reply.

## Extending: add a new provider

Create a new addon (don't modify `muk_ai`). Subclass `ProviderBase`:

```python
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
```

Register it by mutating the imported `REGISTRY` from your addon's
`__init__.py` chain (runs at import time, before any session needs it):

```python
# muk_ai_mistral/providers/__init__.py
from odoo.addons.muk_ai.providers import REGISTRY

from .mistral import MistralProvider

REGISTRY[MistralProvider.name] = MistralProvider
```

Add `<record id="provider_mistral" model="muk_ai.provider">` to
`data/provider.xml` and matching `muk_ai.model` seeds in
`data/model.xml`. Depend on `muk_ai` in your `__manifest__.py`.
Selection, default-model lookup, capability probes, and dispatch all
pick it up automatically.

## Extending: add MCP tools

Agents inherit every tool registered via the `muk_mcp` pattern (see
`muk_mcp`'s README for the full guide). To scope a tool to the
in-Odoo agent only, set the decorator's `registry='odoo'`; external
MCP clients keep seeing the default `mcp` surface only.

## Security & Audit

Every session carries a JSON-serialised tool log covering user
messages, tool calls, tool results, assistant text, `ask_user`
prompts, and answers. Combined with `muk_mcp`'s own audit log, every
AI-driven read or write on your data is traceable end-to-end.

The per-provider idle watchdog aborts dead connections. Runaway loops
are capped by `MAX_ITERATIONS` (default 20) per slice and
`MAX_TOOL_CALLS_PER_ROUND = 10`; an `ask_user`-at-cap edge is handled
gracefully so resumed sessions do not get stuck.

Long turns are sliced across cron ticks instead of dying. Each worker
run gets a wallclock budget bounded below the cron process limit
(`limit_time_real_cron`, falling back to `limit_time_real`) so it yields
*before* Odoo kills the worker; at the boundary the session stays
`running` and re-triggers a worker, resuming from its persisted
conversation on the next tick — the same batch-cron pattern Odoo uses
elsewhere. A per-turn wallclock budget and an optional per-turn cost
limit bound total work. All four caps are set from **Settings > General
Settings > MuK AI** (Iteration Limit, Turn Runtime, Slice Runtime, Cost
Limit) and stored as the `muk_ai.max_iterations`,
`muk_ai.turn_wallclock_seconds`, `muk_ai.slice_wallclock_seconds` and
`muk_ai.turn_cost_limit` system parameters.

Sessions inherit `bus.listener.mixin` and route streaming events
through the owner's partner channel — not a guessable string — so one
user cannot eavesdrop on another.

## Installation

Download the module and add it to your Odoo addons folder. Log into
your Odoo server, open the Apps menu, enable developer mode, click
**Update Apps List**, and install **MuK AI**.

## Upgrade

Download the updated module, replace the folder in your addons path,
restart the server, open the Apps menu, find **MuK AI**, and click
Upgrade.

## Credits

**Contributors**

- Mathias Markl &lt;mathias.markl@mukit.at&gt;
- Kerrim Abd E-Hamed &lt;kerrim.adbelhamed@mukit.at&gt;

**Author &amp; Maintainer**

This module is maintained by [MuK IT GmbH](https://www.mukit.at/). MuK
IT is an Austrian company specialized in customizing and extending
Odoo. Contact: sale@mukit.at or https://mukit.at.
