# MuK AI — Agentidoo Connector

Adds **Agentidoo** as a provider to [`muk_ai`](https://gitlab.mukit.at/odoo-addons/muk_ai)
so the in-Odoo chat routes to **Aimee**, the Agentidoo AI assistant, instead
of directly to an LLM like OpenAI or Anthropic. Aimee runs server-side on
the Agentidoo platform, understands your Odoo data through the
`odoo-connector` bridge, and can drive the Odoo UI through validated
frontend actions.

Ships an in-Odoo onboarding wizard that does the full setup in five
steps without leaving Odoo.

## Requirements

- Odoo 19 (CE or EE)
- [`muk_ai`](https://gitlab.mukit.at/odoo-addons/muk_ai) 19.0.1.0.0 or newer
- An Agentidoo account with an API key — sign up at
  [`agentidoo.com`](https://agentidoo.com) (SaaS) / API at
  `https://api.agentidoo.com` and complete the workspace onboarding before
  running the Odoo-side wizard.

## Installation

```bash
./odoo-bin -c <config> -d <db> -i muk_ai_agentidoo --stop-after-init
```

The module is listed under **Apps → Custom → Agentidoo**. On first
install, go to **Settings → General Settings → Agentidoo** and click
**Run Onboarding**, or open **MuK AI → Agentidoo Onboarding** from the
main menu.

## Onboarding

The wizard has five steps:

1. **Welcome** — short intro and a **Sign Up at agentidoo.com** button
   that opens the Agentidoo dashboard in a new tab.
2. **API Key** — paste the key from *agentidoo.com → Dashboard →
   Settings → API Keys*. The wizard verifies it live against
   `GET /api/v1/me` before continuing.
3. **Acting User** — pick who Aimee acts as when running tool calls
   against Odoo. Three options:
   - **Use my own account** *(default, zero extra cost)* — Aimee acts
     as the installing user.
   - **Pick another internal user** — any non-portal active user.
   - **Create a dedicated `agentidoo-bot` user** *(+1 paid seat on
     Odoo Enterprise)* — the wizard creates it with a random 32-char
     password.
4. **Register Odoo** — sends `POST /api/v1/odoo` with the acting user's
   login + password so Agentidoo can drive the Odoo tools. The password
   is sent once, encrypted in LCP Secrets on the platform side, and
   **never persisted in Odoo**.
5. **Done** — switches `muk_ai.provider` to `agentidoo` and opens the
   chat.

**Skipping step 4** — if your Odoo is not publicly reachable (localhost,
private network, dev instance), click **Skip (use chat only)** on the
Acting User step. Chat with Aimee still works; Aimee just cannot drive
your Odoo tools until you register the instance from a reachable URL.

## Configuration

Settings live on the **muk_ai.provider** record named `agentidoo`
(Settings → Technical → AI → Providers):

| Field | Purpose |
|-------|---------|
| API URL | Agentidoo API base URL (default `https://api.agentidoo.com`). Self-hosted or in-cluster deployments override this to e.g. `http://agentidoo-service.agentidoo-service.svc.cluster.local:8080`. |
| API Key | Bearer token (masked). |
| Agentidoo Acting User | Odoo user Aimee acts as. |
| Session Registered | `true` after a successful `/api/v1/odoo` call. |

Buttons on the provider form:

- **Run Onboarding** / **Re-run Onboarding** — reopens the wizard.
- **Test Connection** — hits `GET /api/v1/me` and toasts the result.

## Architecture

Agentidoo exposes a public HTTP contract called **AAP v1** (Agentidoo
Agent Protocol v1). The `muk_ai_agentidoo` provider is an AAP v1 client;
any AAP-conformant backend (today: kon-brain; tomorrow: anything) works
without client changes.

```
┌────────────────────────────────────┐       ┌───────────────────────────────────────┐
│ muk_ai chat UI (OWL)               │       │ api.agentidoo.com — AAP v1            │
│                                    │       │                                       │
│ muk_ai.session._run_to_completion  │       │ POST /api/v1/chat/sessions            │
│           ↓                        │──────→│ POST /api/v1/chat/sessions/{id}/      │
│ AgentidooProvider.request()        │       │      messages                         │
│ (threads session_id through a      │       │ GET  /api/v1/chat/sessions/{id}/stream│
│  context bag)                      │       │ GET  /api/v1/me                       │
│ SSE events: text_delta, tool_start,│       │ POST /api/v1/odoo                     │
│ tool_result, agent_end             │       │ GET  /api/v1/capabilities             │
└────────────────────────────────────┘       └──────────────────┬────────────────────┘
                                                                ↓
                                                        kon-brain (Aimee)
                                                        odoo-connector
                                                        billing-service
```

Session IDs persist on `muk_ai.session.agentidoo_session_id` so every
turn in an Odoo chat maps 1:1 to an Agentidoo session on the platform.
The provider extends `muk_ai` without modifying it — `AgentidooProvider`
registers itself into `muk_ai.providers.REGISTRY` at import time.

Tool calls are executed **server-side** on the Agentidoo platform.
The provider surfaces them to the UI through `on_delta('tool_start', …)`
and collects `odoo_frontend_action` / `owlet` / `odoo_action_buttons`
tool results for the Odoo frontend, but returns `tool_calls: []` so the
local `muk_ai.session` loop does not re-dispatch them.

## Known limitations

- **Localhost registration** — `POST /api/v1/odoo` is rejected by the
  platform when the Odoo URL is not publicly reachable. Use the
  **Skip** option on the Acting User step during dev.
- **Frontend Actions v1.1** (`odoo_frontend_action` tool,
  `frontend_context` bundle, live OWL dispatcher) is out of scope for
  the v1.0 release and will land in a future version.

## Testing

```bash
./odoo-bin -c <config> -d <db> --test-enable -u muk_ai_agentidoo --stop-after-init
```

Unit tests cover the provider adapter (session creation, session-id bag
threading, auth headers, missing-key behaviour, SSE parsing, capabilities
cache) and the onboarding state machine (all step transitions,
acting-user modes, validation errors, HTTP 401/402 surfacing).

## License

LGPL-3. Copyright MuK IT GmbH.
