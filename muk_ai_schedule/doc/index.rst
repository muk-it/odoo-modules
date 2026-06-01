===============
MuK AI Schedule
===============

Run AI agents on a schedule, let them pause and resume themselves.
**MuK AI Schedule** extends ``muk_ai`` with cron-driven, autonomous
agent sessions: admins define ``muk_ai.schedule`` records that fire
on a chosen cadence, each one launching a fresh ``muk_ai.session``
under a chosen agent and prompt with no user in the loop. A
per-record dispatch mode fans a single schedule into one session
per record matching a domain (or arbitrary Python), and chained
sessions expose the previous run's transcript so an agent can recall
what it did last time without burning context.

Two in-session MCP tools let the agent pace itself across cron
ticks: ``schedule_resume`` defers the current session to a
wall-clock time (and injects a synthetic user message on wake-up so
the agent remembers what it was waiting for), ``schedule_recurring``
re-fires the same session on a fixed cadence with hard caps.
Sessions linked to a business record mirror their start to that
record's chatter so every AI run a record spawned stays visible
from the record itself.

This is a pure runtime extension on top of ``muk_ai``'s session and
tool registry: no new providers, no new chat client, no fork — only
``_inherit`` overrides plus a single dedicated cron worker.

Installation
============

To install this module, you need to:

Download the module and add it to your Odoo addons folder. Afterward,
log on to your Odoo server and go to the Apps menu. Trigger the debug
mode and update the list by clicking on the "Update Apps List" link.
Now install the module by clicking on the install button. Requires
``muk_ai`` and the ``croniter`` Python package.

Upgrade
=======

To upgrade this module, you need to:

Download the module and add it to your Odoo addons folder. Restart
the server and log on to your Odoo server. Select the Apps menu and
upgrade the module by clicking on the upgrade button.

What's in the box
=================

- **muk_ai.schedule model** — name, agent, prompt, recurrence
  (minute/hour/day/week/month/cron), dispatch mode, target model
  with domain or Python record source, per-record caps, owner, and
  prompt revision history via the reusable
  ``muk_ai.revision.mixin`` from ``muk_ai``.
- **muk_ai.session extension** — ``schedule_id``,
  ``previous_session_id``, ``res_model`` / ``res_id``, a new
  ``schedule`` state, ``resume_at``, ``recur_config`` JSON,
  ``recur_runs_done``, and a ``resume_prompt`` text injected as a
  synthetic user message on wake-up.
- **schedule_resume MCP tool** — pauses the current session until a
  wall-clock time (``at`` ISO 8601 or ``seconds_from_now``, capped
  at 60 s … 30 days) and stores a required ``prompt`` to fire on
  resume.
- **schedule_recurring MCP tool** — pauses the current session and
  re-fires it every ``every`` seconds (60 s … 30 days), bounded by
  either ``until`` or ``max_runs``. The required ``prompt`` supports
  ``{run}`` / ``{total}`` placeholders.
- **Fire Due Schedules cron** — dedicated 1-minute worker that
  sweeps active schedules with ``next_call <= now``, claims an
  advisory lock per schedule, and dispatches sessions; the existing
  ``muk_ai`` session crons then run those sessions to completion.
- **Schedule countdown widget** — live, bus-driven ``Nd Nh`` /
  ``Nm Ns`` countdown rendered on ``next_call`` (schedule
  list/kanban/form) and ``resume_at`` (session form Schedule tab).
  Updates without a page reload as the cron worker advances times.
- **Session views** — Schedule notebook tab on the session form,
  schedule + scheduled filters in the search, ``schedule_id``
  column in the session list, and a *Chain* stat button that opens
  every session linked through ``previous_session_id``.
- **Manage menu link** — *MuK AI > Schedules* (and
  ``/odoo/ai-schedules``).

Building a schedule
===================

Open *MuK AI > Schedules* and create a record:

- **Name** — display label only.
- **Agent** — required. The agent that runs every spawned session.
  Approval mode, system prompt, tool filter, model, read-only flag
  and essentials list are all inherited from the agent record.
- **Owner** — ``res.users`` whose access rights spawned sessions
  run under. Defaults to the schedule's creator.
- **Recurrence** — pick one:

  - ``Minutes / Hours / Days`` — fixed-delta repeats every N units.
  - ``Weeks`` — fires every N weeks on the chosen weekday.
  - ``Months`` — fires every N months on the chosen day-of-month
    (auto-clamps to last day of the month for short months).
  - ``Cron Expression`` — standard 5-field cron string evaluated
    by ``croniter``; takes precedence over the simple delta fields.

- **Dispatch Mode**:

  - ``Single`` — one session per fire. The prompt template gets
    the full ``records`` recordset resolved from the target model.
  - ``Per Record`` — one session per record matching the source.
    The target model is required; sessions inherit ``res_model`` /
    ``res_id`` from each record and mirror to its chatter.

- **Target Model** — ``ir.model`` used to resolve ``records``.
  Required for per-record mode, optional for single mode (only
  needed when the prompt template references ``records``).
- **Record Source**:

  - ``Domain`` — simple Odoo domain on the target model.
  - ``Python`` — safe-evaluated code that must assign a recordset
    to the ``records`` variable. Available context: ``env``,
    ``now``, ``today``, ``datetime``, ``date``, ``time``,
    ``timedelta``, ``relativedelta``.

- **Max Records Per Fire** — per-record cap; spawned sessions are
  capped to the first N matches.
- **Prompt** — required. Initial user message sent to the agent on
  every fire. Rendered as an inline template with the placeholders
  listed below.
- **Caps** — per-session overrides for the four hard limits
  (resumes, lifetime hours, total tokens, cost EUR). Leave at ``0``
  to inherit the module defaults (``50``, ``720``, ``1_000_000``,
  ``5.0``).

A **Run Now** button on the form fires the schedule immediately and
opens the spawned session(s) without waiting for the cron worker.
**Sessions** and **Prompt History** stat buttons surface every
session ever launched by this schedule and every prior version of
the prompt template.

Prompt template placeholders
----------------------------

The schedule prompt is rendered with Odoo's inline-template engine.
Available placeholders:

- ``{{ user }}`` — the schedule owner.
- ``{{ company }}`` — the active company.
- ``{{ today }}`` — ISO date.
- ``{{ now }}`` — full datetime.
- ``{{ env }}`` — full Odoo environment for ad-hoc lookups.
- ``{{ record }}`` — per-record mode: the current record. Empty
  recordset in single mode.
- ``{{ records }}`` — single mode: the resolved recordset. Empty
  recordset in per-record mode.
- ``{{ previous_session }}`` — proxy over the prior run's session
  in this chain. ``previous_session.last_text`` returns the
  previous assistant reply; ``previous_session.tool_log`` returns
  a list of ``{name, arguments, output}`` dicts. Empty proxy on
  the first run or when no chain exists.

Render failures fall back to the raw prompt and log a
``prompt_render_error`` event on the spawned session, so a broken
template never silently swallows a fire.

Self-pacing tools
=================

Sessions started by a schedule (or any session, for that matter)
can defer themselves through two ``@mcp_tool`` methods registered
on the ``odoo`` registry:

.. code-block:: text

    schedule_resume(prompt="Re-check overdue invoices.", seconds_from_now=3600)
    schedule_resume(prompt="Wake at COB to summarize the day.", at="2026-05-05T17:00:00Z")

``schedule_resume`` writes ``state='schedule'``, sets ``resume_at``
to the target time, persists the ``prompt`` argument as
``resume_prompt``, and returns
``{"ok": true, "resume_at": "..."}``. When the dedicated cron
sweep fires at or after ``resume_at``, the session re-enters the
runtime and the stored prompt is injected as a synthetic user turn,
so the agent picks up exactly where it left off — with the
instruction it gave itself fresh in context.

.. code-block:: text

    schedule_recurring(prompt="Daily digest run #{run} of {total}.", every=86400, max_runs=7)
    schedule_recurring(prompt="Watch for new high-value leads.", every=900, until="2026-05-30T00:00:00Z")

``schedule_recurring`` is the same flow plus persistent recurrence
state in ``recur_config`` (``every``, ``until``, ``max_runs``,
``started_at``, ``prompt``). On every fire the session re-enters
the runtime, the prompt is rendered with ``{run}`` (current
iteration) and ``{total}`` (``max_runs`` or ``∞``), and
``recur_runs_done`` is incremented. When ``recur_runs_done`` reaches
``max_runs`` or ``now > until``, the session finishes naturally
instead of redeferring.

Both tools enforce the per-session hard caps before re-deferring;
hitting any cap aborts the recurrence with a ``cap_exceeded`` event
and an explicit error state so a runaway agent can never bill
unbounded.

Per-record dispatch and chaining
================================

In ``Per Record`` mode the schedule resolves its target recordset
on every fire and creates one session per record (capped by
``max_records_per_fire``). Each spawned session carries:

- ``schedule_id`` — the source schedule.
- ``previous_session_id`` — last session for the same
  ``(schedule_id, res_model, res_id)`` tuple, or unset on first run.
  Single-mode sessions chain by ``(schedule_id, no record)``.
- ``res_model`` / ``res_id`` — the dispatched record. The session
  posts an internal note to that record's chatter
  (``mail.mt_note``) with a back-link to the session form, so
  every AI run a record spawned is visible from the record itself.

The previous-session proxy means a digest agent can prompt itself
with ``"Last week you covered X. Avoid repeating it."`` and see only
the necessary text — not a full conversation transcript pasted into
context. The prompt template can pull
``previous_session.last_text`` for the assistant reply, or walk
``previous_session.tool_log`` to see what tools the prior run
called.

Hard caps
=========

Every spawned session is bounded by four limits, configurable per
schedule and falling back to module-wide defaults when left at
``0``:

+------------------------+--------------+---------------------------------------------------+
| Cap                    | Default      | What it checks                                    |
+========================+==============+===================================================+
| ``max_resumes``        | ``50``       | ``recur_runs_done`` — total resumes/recurring     |
+------------------------+--------------+---------------------------------------------------+
| ``max_lifetime_hours`` | ``720`` (30d)| wall-clock since session create                   |
+------------------------+--------------+---------------------------------------------------+
| ``max_total_tokens``   | ``1_000_000``| ``total_input_tokens + total_output_tokens``      |
+------------------------+--------------+---------------------------------------------------+
| ``max_cost_eur``       | ``5.00``     | ``total_cost``                                    |
+------------------------+--------------+---------------------------------------------------+

The check runs inside ``schedule_resume`` / ``schedule_recurring``
before re-deferring the session. Any breach aborts the session with
``state='error'``, posts a ``cap_exceeded`` event with the
offending cap, observed value and limit, and returns
``{"ok": false, "error": "cap_exceeded", "cap": "<cap>"}`` to the
calling agent so it can recover gracefully.

Cron architecture
=================

Three pieces of plumbing are involved:

1. **MuK AI Schedule: Fire Due Schedules** — dedicated 1-minute
   cron defined by this addon. Sweeps active schedules with
   ``next_call <= now``, takes a Postgres advisory lock per
   schedule id, dispatches sessions inside a savepoint, then
   advances ``last_call`` and recomputes ``next_call``. The lock
   means two workers never fire the same schedule on the same
   tick.
2. **muk_ai's session crons** — the existing pending-session
   workers. They pick up newly spawned sessions and run them to
   completion. They also pick up ``state='schedule'`` sessions
   whose ``resume_at`` is due, write the resume prompt as a
   synthetic user turn, and re-enter the runtime.
3. **schedule_resume / schedule_recurring** — in-session MCP tools
   that *write* ``state='schedule'`` and ``resume_at``. They never
   touch crons directly; the existing workers handle the pickup.

This separation means the addon is a single cron worker plus a
handful of ``_inherit`` overrides — no fork of ``muk_ai`` and no
duplicate scheduling logic.

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
