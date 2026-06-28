# MuK AI Schedule

Run AI agents on a schedule, let them pause and resume themselves.
**MuK AI Schedule** turns a `muk_ai.schedule` record into a cron-driven,
autonomous agent session: define a record that fires on a chosen
cadence, and each fire launches a fresh `muk_ai.session` under a chosen
agent and prompt with no user in the loop.

Each schedule **owns** its own `ir.actions.server` (an `ai_agent`
action contributed by `muk_ai_automation`) plus a dedicated `ir.cron` —
one cron per schedule. The cron simply runs the owned action; all the
heavy lifting (resolving the target recordset, rendering the prompt,
spawning and chaining sessions, mirroring to chatter) is provided by
the `muk_ai_automation` dependency. This module is the thin scheduling
layer on top: it provisions and keeps the owned action + cron in sync,
adds self-pacing tools to sessions, and exposes a schedule UI.

Two in-session MCP tools let the agent pace itself across cron ticks:
`schedule_resume` defers the current session to a wall-clock time (and
injects a synthetic user message on wake-up so the agent remembers what
it was waiting for), `schedule_recurring` re-fires the same session on a
fixed cadence with hard caps.

This is a pure runtime extension: no new providers, no new chat client,
no fork of `muk_ai` — only `_inherit` overrides plus per-schedule owned
records.

## What's in the box

- **`muk_ai.schedule` model** — name, agent, prompt, recurrence
  (minute/hour/day/week/month/cron), dispatch mode, target model with
  domain or Python record source, per-session cap overrides, owner, and
  prompt revision history (via the reusable `muk_ai.revision.mixin`
  from `muk_ai`). Each record owns an `action_server_id`
  (`ir.actions.server`, state `ai_agent`) and a `cron_id` (`ir.cron`),
  both provisioned on create, synced on write, and cleaned up on
  unlink.
- **`muk_ai.session` extension** — a new `schedule` state, `schedule_id`
  back-link, `resume_at`, `recur_config` JSON, `recur_runs_done`, a
  `resume_prompt` text injected as a synthetic user message on wake-up,
  and a `chain_session_count`. The session-to-record link
  (`previous_session_id`, `res_model` / `res_id`) and chatter mirroring
  are contributed by the `muk_ai_automation` dependency.
- **`schedule_resume` MCP tool** — pauses the current session until a
  wall-clock time (`at` ISO 8601 or `seconds_from_now`, capped at
  60 s … 30 days) and stores a required `prompt` to fire on resume.
- **`schedule_recurring` MCP tool** — pauses the current session and
  re-fires it every `every` seconds (60 s … 30 days), bounded by either
  `until` or `max_runs`. The required `prompt` supports `{run}` /
  `{total}` placeholders.
- **Per-schedule owned cron** — each schedule's `ir.cron` runs that
  schedule's owned server action on its cadence. There is no central
  sweep and no advisory lock; isolation comes from one cron per
  schedule.
- **Session pickup overrides** — this module extends `muk_ai`'s own
  pending-session crons to wake `state='schedule'` sessions whose
  `resume_at` has elapsed, inject the stored resume prompt, and hand
  them back to the existing runtime. No dedicated cron is added for
  resumes.
- **Schedule countdown widget** — live, bus-driven `Nd Nh` / `Nm Ns`
  countdown rendered on `next_call` (schedule list/kanban/form) and
  `resume_at` (session form Schedule tab). Updates without a page
  reload as the cron advances times.
- **Session views** — Schedule notebook tab on the session form,
  schedule + scheduled filters in the search, `schedule_id` column in
  the session list, and a *Chain* stat button that opens every session
  linked through `previous_session_id`.
- **Schedules menu** — *MuK AI > Schedules* (and `/odoo/ai-schedules`).

## How a schedule is built

Open *MuK AI > Schedules* and create a record:

- **Name** — display label, also used to name the owned action and
  cron.
- **Agent** — required. The agent that runs every spawned session.
  Approval mode, system prompt, tool filter, model, read-only flag and
  essentials list are all inherited from the agent record.
- **Owner** — `res.users` the owned cron runs as; spawned sessions run
  under this user's access rights. Defaults to the schedule's creator.
- **Recurrence** — pick one:
  - `Minutes / Hours / Days` — fixed-delta repeats every N units.
  - `Weeks` — fires every N weeks on the chosen weekday.
  - `Months` — fires every N months on the chosen day-of-month
    (auto-clamps to last day of the month for short months).
  - `Cron Expression` — standard 5-field cron string evaluated by
    `croniter`. The owned cron's next fire time is computed from the
    expression.
- **Dispatch Mode**:
  - `Single` — one session per fire. The prompt template gets the full
    `records` recordset resolved from the target model.
  - `Per Record` — one session per record matching the source. The
    target model is required; spawned sessions inherit `res_model` /
    `res_id` from each record, chain through `previous_session_id`, and
    mirror a note to that record's chatter.
- **Target Model** — `ir.model` used to resolve `records`. Required for
  per-record mode, optional for single mode (only needed when the
  prompt template references `records`). Defaults to the AI session
  model when left unset.
- **Record Source**:
  - `Domain` — simple Odoo domain on the target model.
  - `Python` — safe-evaluated code that must assign a recordset to the
    `records` variable. Available context: `env`, `now`, `today`,
    `datetime`, `date`, `time`, `timedelta`, `relativedelta`. Useful
    for "overdue", "this week", or cross-model lookups.
- **Max Records Per Fire** — per-record cap; spawned sessions are capped
  to the first N matches.
- **Prompt** — required. Initial user message sent to the agent on every
  fire. Rendered as an inline template with the placeholders listed
  below.
- **Caps** — per-session overrides for the four hard limits (resumes,
  lifetime hours, total tokens, cost EUR). Leave at `0` to inherit the
  module defaults (`50`, `720`, `1_000_000`, `5.00`).

A **Run Now** button on the form provisions the owned action if needed,
fires it immediately, advances the owned cron's `last_call` / `next_call`,
and opens the spawned session(s) without waiting for the cron. **Sessions**
and **Prompt History** stat buttons surface every session ever launched by
this schedule and every prior version of the prompt template.

### Prompt template placeholders

The schedule prompt is rendered with Odoo's inline-template engine. The
schedule contributes `{{ now }}`; the dispatch layer
(`muk_ai_automation`) contributes `{{ record }}`, `{{ records }}` and
`{{ previous_session }}`. Available placeholders:

- `{{ user }}` — the schedule owner.
- `{{ company }}` — the active company.
- `{{ today }}` — ISO date.
- `{{ now }}` — full datetime.
- `{{ env }}` — full Odoo environment for ad-hoc lookups
  (`env['res.partner'].search_count(...)` etc.).
- `{{ record }}` — per-record mode: the current record. Empty recordset
  in single mode.
- `{{ records }}` — single mode: the resolved recordset. Empty recordset
  in per-record mode.
- `{{ previous_session }}` — proxy over the prior run's session in this
  chain. `previous_session.last_text` returns the previous assistant
  reply; `previous_session.tool_log` returns a list of
  `{name, arguments, output}` dicts. Empty proxy on the first run, in
  single mode, or when no chain exists.

Render failures fall back to the raw prompt and log a
`prompt_render_error` event on the spawned session, so a broken template
never silently swallows a fire.

## How an agent paces itself

Sessions started by a schedule (or any session, for that matter) can
defer themselves through two `@mcp_tool` methods registered on the
`odoo` registry:

```text
schedule_resume(prompt="Re-check overdue invoices.", seconds_from_now=3600)
schedule_resume(prompt="Wake at COB to summarize the day.", at="2026-05-05T17:00:00Z")
```

`schedule_resume` writes `state='schedule'`, sets `resume_at` to the
target time, persists the `prompt` argument as `resume_prompt`, and
returns `{"ok": true, "resume_at": "..."}`. When `muk_ai`'s
pending-session cron next runs at or after `resume_at`, the session
re-enters the runtime and the stored prompt is injected as a synthetic
user turn, so the agent picks up exactly where it left off — with the
instruction it gave itself fresh in context.

```text
schedule_recurring(prompt="Daily digest run #{run} of {total}.", every=86400, max_runs=7)
schedule_recurring(prompt="Watch for new high-value leads.", every=900, until="2026-05-30T00:00:00Z")
```

`schedule_recurring` is the same flow plus persistent recurrence state in
`recur_config` (`every`, `until`, `max_runs`, `started_at`, `prompt`). On
every fire the session re-enters the runtime, the prompt is rendered with
`{run}` (current iteration) and `{total}` (`max_runs` or `∞`), and
`recur_runs_done` is incremented. When the session finishes and
`recur_runs_done` reaches `max_runs` or `now > until`, the session stops
redeferring instead of re-arming.

Both tools enforce the per-session hard caps before re-deferring; hitting
any cap aborts the recurrence with a `cap_exceeded` event and an explicit
error state so a runaway agent can never bill unbounded.

## Per-record dispatch and chaining

In `Per Record` mode the owned action resolves its target recordset on
every fire and creates one session per record (capped by
`max_records_per_fire`). Each spawned session carries:

- `schedule_id` — back-link to the source schedule (set because the
  session inherits the schedule's owned action).
- `previous_session_id` — last session for the same
  (`owned action`, `res_model`, `res_id`) tuple, or unset on first run.
- `res_model` / `res_id` — the dispatched record. `muk_ai_automation`
  posts an internal note to that record's chatter with a back-link to
  the session, so every AI run a record spawned is visible from the
  record itself.

Single dispatch mode runs one session per fire and does **not** chain —
there is no per-record key to chain on, so `previous_session` is always
an empty proxy there.

The previous-session proxy means a digest agent can prompt itself with
`"Last week you covered X. Avoid repeating it."` and see only the
necessary text — not a full conversation transcript pasted into context.
The prompt template can pull `previous_session.last_text` for the
assistant reply, or walk `previous_session.tool_log` to see what tools
the prior run called.

The Chain stat button on the session form opens every session linked
through `previous_session_id`, walking both directions, so operators can
see the full recurrence history at a glance.

## Hard caps

Every spawned session is bounded by four limits, configurable per
schedule and falling back to module-wide defaults when left at `0`:

| Cap                     | Default      | What it checks                                              |
|-------------------------|--------------|-------------------------------------------------------------|
| `max_resumes`           | `50`         | `recur_runs_done` — total resumes/recurring fires           |
| `max_lifetime_hours`    | `720` (30 d) | wall-clock since session create                             |
| `max_total_tokens`      | `1_000_000`  | `total_input_tokens + total_output_tokens`                  |
| `max_cost_eur`          | `5.00`       | `total_cost`                                                |

The check runs inside `schedule_resume` / `schedule_recurring` before
re-deferring the session. Any breach aborts the session with
`state='error'`, posts a `cap_exceeded` event with the offending cap,
observed value and limit, and returns
`{"ok": false, "error": "cap_exceeded", "cap": "<cap>"}` to the calling
agent so it can recover gracefully.

## Architecture

Three pieces of plumbing are involved, and most of the work is delegated:

1. **Per-schedule owned action + cron** — on create, each
   `muk_ai.schedule` provisions an `ir.actions.server` (state
   `ai_agent`, from `muk_ai_automation`) carrying the agent, prompt,
   dispatch mode, record source and caps, plus a dedicated `ir.cron`
   that runs that action on the schedule's cadence. Writes sync the
   mutated config onto both; unlink best-effort removes them. One cron
   per schedule means two schedules never contend — there is no central
   sweep and no Postgres advisory lock.
2. **`muk_ai_automation` dispatch** — the owned action's `ai_agent`
   state resolves the target recordset, renders the prompt, spawns and
   chains sessions, and mirrors notes onto linked records' chatter. This
   module does not implement dispatch or chatter itself; it depends on
   `muk_ai_automation` for them.
3. **`muk_ai`'s session crons** — the existing pending-session workers
   run newly spawned sessions to completion. This module extends them to
   also wake `state='schedule'` sessions whose `resume_at` is due, write
   the resume prompt as a synthetic user turn, and re-enter the runtime.

This separation keeps the addon a thin scheduling layer plus a handful of
`_inherit` overrides — no fork of `muk_ai` and no duplicate dispatch
logic.

## Installation

Download the module and add it to your Odoo addons folder. Log into your
Odoo server, open the Apps menu, enable developer mode, click **Update
Apps List**, and install **MuK AI Schedule**. Requires
`muk_ai_automation` (which pulls in `muk_ai`) and the `croniter` Python
package.

## Upgrade

Download the updated module, replace the folder in your addons path,
restart the server, open the Apps menu, find **MuK AI Schedule**, and
click Upgrade.

## Credits

**Contributors**

- Mathias Markl &lt;mathias.markl@mukit.at&gt;

**Author &amp; Maintainer**

This module is maintained by [MuK IT GmbH](https://www.mukit.at/). MuK IT
is an Austrian company specialized in customizing and extending Odoo.
Contact: sale@mukit.at or https://mukit.at.
