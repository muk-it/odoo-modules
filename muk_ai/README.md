# MuK AI

Brings an agentic AI assistant inside Odoo. MuK AI wires a configurable
LLM provider, a session-based agent runtime, and a native OWL chat
client into your existing Odoo instance. The assistant talks to your
data through the same `muk_mcp` tool registry your external AI clients
already use — one source of truth, one permission model, one audit
trail.

Ships with two first-class providers (**OpenAI** and **Anthropic**),
live token streaming, human-in-the-loop `ask_user` support, per-agent
tool filters, read-only scope enforcement, multimodal attachments
(images, PDFs, text files), and a daily usage cron. Adding a new
provider is a single-file drop-in — the built-in provider registry
drives dispatch, settings Selection, and default model/URL fallbacks.

## Configuration

**Provider Settings**

Open **Settings > General Settings > MuK AI** to configure:

- **AI Provider** — `OpenAI` or `Anthropic`. The Selection is derived
  from the provider registry, so adding a provider adds an option
  automatically.
- **API Key** — Provider API key. Stored in `ir.config_parameter`
  under `muk_ai.api_key`.
- **API URL** — Optional override. Leave empty to use the provider's
  default (`https://api.openai.com/v1` or
  `https://api.anthropic.com/v1`).
- **Model** — Optional override. Leave empty to use the provider's
  default (`gpt-4o-mini` or `claude-sonnet-4-5`).
- **Max Tokens** — Cap on completion tokens per request (default
  `4096`).
- **Timeout** — HTTP timeout for non-streaming calls (default `60s`).
- **Rate Limit (per minute)** — Maximum sessions a single user may
  create per minute. `0` disables the cap.
- **Stream Idle Timeout** — Seconds without a streamed chunk before
  the connection is aborted and the session is marked errored
  (default `45s`).
- **Max Attachment Size (MiB)** — Hard cap on any single attachment
  sent with a user message (default `20`).
- **Text Attachment Inline Limit (KiB)** — Text attachments
  (`txt`/`csv`/`md`) are inlined into the user message and truncated
  past this cap (default `256`).

A **Test Connection** button hits the current provider with a tiny
`Reply with a single word.` prompt and reports success or failure
without leaving the page.

**Access Groups**

- **Internal User** (`base.group_user`) — Can open the chat, manage
  their own sessions, read agents.
- **System** (`base.group_system`) — Can manage every session, edit
  agents and configure providers/models.

**Rate Limit & Usage Cron**

The per-user rate limit throttles session creation. A daily cron job
(`MuK AI: Log Daily Usage`) aggregates token consumption per user and
writes it to the Odoo log for cost attribution.

## Usage

**Chatting**

Open **MuK AI > Chat**. Create a new session from the sidebar, pick an
agent (optional), type a message, and hit `Enter`. The reply streams
in live via the Odoo bus; tool calls render inline as collapsible cards
with live-filling arguments, so you always see what the model is doing
before it runs. `Shift+Enter` inserts a newline; a single Send/Stop
toggle cancels an in-flight stream.

A systray icon in the top bar surfaces running sessions across the UI
and lets you pop out a floating Discuss-style chat window so you can
keep talking while navigating other views.

**Write-tool safety**

Risky write calls pause the session and ask before running.
An update to a mail-tracked field, a workflow method like
``action_post`` on an invoice, a deletion, or a creation on a
high-impact model triggers an approval card inline in the chat.
The card shows why it fired ("approving because ``state`` is
tracked on ``account.move``"), the proposed JSON arguments, and
three buttons:

- **Approve once** — dispatches the call and logs the decision.
- **Always allow** — same, plus persists a rule that auto-approves
  matching calls in every future session for this (user, agent,
  tool, model, sensitive-fields) combination.
- **Reject** — returns a ``rejected_by_user`` tool output to the
  model so it can recover (clarify, propose a safer alternative).

All decisions are stored under **MuK AI → Approval Log** with the
proposed vs. executed arguments. Saved rules live under
**MuK AI → Approval Rules** and can be removed there. Per-agent
``Approval Mode`` lets unattended agents skip the prompt
entirely (``Never ask``).

**View context**

Whenever a floating chat window is open, the session sticks to the
Odoo view the user is looking at (form record, list, kanban, pivot,
graph). A header pill shows the pinned context (e.g.
`sale.order · SO-00042`) and opens that view on click. Navigation
fired by the agent (`open_record`, `open_view`, `open_action`) updates
the pin automatically — so follow-up turns stay oriented even as the
assistant steers the user around. The context is injected at request
time as a short `<ui_ctx>` tag at the tail of the conversation, so the
model can resolve references like "this order" or "the current list"
without any extra tool call. Type `/unpin` to clear it.

**Attachments**

Drop a file onto the composer, paste a screenshot, or click the clip
icon to pick one. Images are rendered inline, PDFs and text files
show as pills. On send, every attachment is streamed to the active
provider as a native content block — `input_image` / `input_file` for
OpenAI Responses, `image` / `document` blocks for Anthropic Messages,
inline text for small `.txt` / `.csv` / `.md` files. Accepted types:
PNG, JPEG, WebP, GIF, PDF, plain text, CSV, Markdown. Capped at 20 MiB
per file (configurable) with oversize and unknown-type uploads
rejected server-side.

**Human-in-the-loop**

When the LLM calls the `ask_user` tool, the session pauses in
`waiting_user` state and surfaces the question in the chat. Your answer
is fed back as a `function_call_output` so the model resumes the turn
exactly where it left off.

**Context-window meter**

The chat header shows a colour-coded battery pill with the share of
the model's context window consumed by the last turn's input. Green
below 70%, amber up to 90%, red above. Agents carry an optional
`model_context_window` override; unset falls back to a built-in
lookup table for the popular OpenAI and Anthropic models.

**Slash commands**

Start a message with `/` to open a pop-up of available commands:

- `/help` — inline cheat sheet
- `/clear` — confirm and wipe the current conversation + tool log,
  keeping the session record and agent
- `/compact` — ask the provider for a ≤500-token summary and replace
  the conversation with it, freeing context without losing continuity

The composer warns at 85% context usage and auto-compacts at 95%.

**Agents**

Open **MuK AI > Agents**. An agent is a named preset: system prompt,
model override, temperature, history limit, read-only flag, and a tool
filter that restricts which MCP tools the LLM can call. Ship a "Sales
Assistant" with write access to leads and a "Read-only Analyst" that
cannot mutate anything — the latter is enforced server-side through
the MCP scope check, not just a prompt instruction.

Record rules keep each user's sessions private (own-only for *AI
User*, full access for *AI Manager*).

## Providers

The provider layer is a thin Odoo `AbstractModel` dispatcher
(`muk_ai.provider`) plus a `providers/` Python package that registers
one class per provider. Each class declares `name / label /
default_model / default_url`, implements `headers()` and `request()`,
and inherits shared HTTP + SSE streaming plumbing from `ProviderBase`.
The settings Selection, default model fallbacks, and dispatch are all
derived from the same `REGISTRY` — adding a new provider is one new
file and one line.

| Provider    | Default model          | Streaming | Notes                                                         |
|-------------|------------------------|-----------|---------------------------------------------------------------|
| `openai`    | `gpt-4o-mini`          | SSE       | OpenAI Responses API; skips `temperature` for reasoning models |
| `anthropic` | `claude-sonnet-4-5`    | SSE       | Messages API; in-dispatcher adapter for tool_use / tool_result |

Both providers emit the same on-delta events (`text`, `tool_start`,
`tool_args`) so the chat UI feels identical regardless of which
provider is active.

## Tool Dispatch via muk_mcp

Agents call exactly the same tool surface as your external MCP
clients — no duplicate catalog, no divergence. The MuK AI agent
registry pulls tools from `muk_mcp` filtered by registry (`ai`), and a
handful of UI-specific tools are registered under the `odoo` registry
for the in-Odoo agent only:

- `open_record` — Navigate the user to a specific record.
- `open_view` — Open a filtered list/kanban/pivot view of a model.
- `open_action` — Launch an existing Odoo action by xmlid or id
  (honouring the action's `groups_id`).
- `show_notification` — Toast a message in the Odoo web client.
- `ask_user` — Pause the session for clarification.

The chat UI auto-dispatches any returned `ir.actions.*` descriptor,
so the model can navigate the user through the UI as part of a reply.

## Extending: add a new provider

Drop a new file under `muk_ai/providers/`:

```python
# muk_ai/providers/gemini.py
from .base import ProviderBase


class GeminiProvider(ProviderBase):
    name = 'gemini'
    label = "Google Gemini"
    default_model = 'gemini-2.5-flash'
    default_url = 'https://generativelanguage.googleapis.com/v1beta'

    def headers(self):
        return {
            'Authorization': f'Bearer {self.api_key}',
            'Content-Type': 'application/json',
        }

    def request(self, inputs, tools_schema=None, text_schema=None,
                temperature=0.1, on_delta=None, model=None):
        model = self.model_for(model)
        body = {'model': model, 'contents': self._to_contents(inputs)}
        ...
        if callable(on_delta):
            for event in self._post_stream('/models/' + model + ':streamGenerateContent', body):
                ...
        return self._parse_response(self._post_json(...))
```

Then add one line to `providers/__init__.py`:

```python
from .gemini import GeminiProvider

REGISTRY = {
    cls.name: cls for cls in (
        OpenAIProvider,
        AnthropicProvider,
        GeminiProvider,
    )
}
```

Selection, default-model/URL fallbacks, and dispatch all pick it up
automatically.

## Extending: add MCP tools

Agents inherit every tool registered via the `muk_mcp` pattern (see
`muk_mcp`'s README for the full guide). To scope a tool to the in-Odoo
agent only, set the decorator's `registry='ai'` or `registry='odoo'`;
the agent dispatches both while external MCP clients see the default
`mcp` surface only.

## Security & Audit

Every session carries a JSON-serialised tool log covering user
messages, tool calls, tool results, assistant text, `ask_user` prompts,
and answers. Combined with `muk_mcp`'s own audit log, every AI-driven
read or write on your data is traceable end-to-end.

Per-stream idle watchdog (`muk_ai.stream_idle_timeout`) aborts dead
connections. Runaway loops are capped by `MAX_ITERATIONS` per turn,
and an `ask_user`-at-cap edge is handled gracefully so resumed
sessions do not get stuck.

Sessions use `bus.listener.mixin` and route events through the owner's
partner channel — not a guessable string — so one user cannot
eavesdrop on another.
