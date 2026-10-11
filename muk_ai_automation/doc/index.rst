=================
MuK AI Automation
=================

Fire a MuK AI agent from any server action, automation rule, or
scheduled action. **MuK AI Automation** extends ``muk_ai`` with a new
``ir.actions.server`` state, ``ai_agent``, that spawns a
``muk_ai.session`` under a chosen agent and prompt whenever the action
runs — with no user in the loop. A per-record dispatch mode fans a
single action into one session per record matching a domain (or
arbitrary Python), and chained sessions expose the prior run so the
agent can recall what it did last time.

Linking a session to the record it ran for — the ``res_model`` /
``res_id`` fields, the chatter note back-linking to it, the *AI
Sessions* box in that record's chatter and the per-record access rules
— belongs to **MuK AI Chatter**, which this module depends on.

Because the agent is just another server-action state, it plugs into
everything that already drives server actions: contextual actions on a
list/form, ``base.automation`` rules reacting to create/write/unlink
events, and ``ir.cron`` scheduled actions firing on a cadence — no new
trigger engine, no fork of ``muk_ai``.

Installation
============

To install this module, you need to:

Download the module and add it to your Odoo addons folder. Afterward,
log on to your Odoo server and go to the Apps menu. Trigger the debug
mode and update the list by clicking on the "Update Apps List" link.
Now install the module by clicking on the install button. Requires
``base_automation`` and ``muk_ai_chatter`` (which brings in ``muk_ai``).

Upgrade
=======

To upgrade this module, you need to:

Download the module and add it to your Odoo addons folder. Restart
the server and log on to your Odoo server. Select the Apps menu and
upgrade the module by clicking on the upgrade button.

What's in the box
=================

- **ai_agent server-action state** — adds the *Run AI Agent* option
  to ``ir.actions.server.state``, with ``_run_action_ai_agent``
  (single record) and ``_run_action_ai_agent_multi`` (multi record)
  handlers that both dispatch through one helper. Available to
  anything that runs a server action: contextual actions,
  ``base.automation`` rules, and ``ir.cron`` scheduled actions.
- **ir.actions.server fields** — ``agent_id``, ``agent_prompt``
  (translatable inline template), ``agent_dispatch_mode``
  (single / per_record), ``agent_record_source`` (domain / Python),
  ``agent_record_domain``, ``agent_record_code``,
  ``agent_max_records_per_fire`` (default ``100``), the four
  per-action caps, and ``agent_chain_strategy`` (none / per_record).
- **muk_ai.session extension** — ``action_server_id``,
  ``base_automation_id`` (related) and ``previous_session_id``, plus
  the prompt scope (``record``, ``records``, ``previous_session``,
  ``now``) and the headless client-kind handling for a session nobody
  is watching. The ``res_model`` / ``res_id`` link itself, the chatter
  mirror and the per-record access rules come from **MuK AI Chatter**.
- **Manage menus** — *MuK AI > AI Automation Rules* (base automation
  rules whose server action is ``ai_agent``) and *MuK AI > AI
  Scheduled Actions* (crons pointing at an ``ai_agent`` server
  action), both restricted to Settings users.

How a server action fires an agent
===================================

Create an ``ir.actions.server`` and set its **Action To Do** to
**Run AI Agent**. The AI Agent section then exposes:

- **Agent** — required when the state is ``ai_agent``. The agent that
  runs every spawned session; approval mode, system prompt, tool
  filter, model and read-only flag all come from the agent record.
- **Agent Dispatch Mode**:

  - ``Single`` — one session per fire. The prompt template receives
    the full ``records`` recordset the action resolves.
  - ``Per Record`` — one session per resolved record. Each session
    inherits ``res_model`` / ``res_id`` from its record and mirrors a
    note to that record's chatter.

- **Agent Record Source** — how the target recordset is resolved when
  the action is not already invoked against records:

  - ``Domain`` — a safe-evaluated Odoo domain
    (``agent_record_domain``, default ``[]``) searched on the action's
    model.
  - ``Python`` — safe-evaluated code (``agent_record_code``) that must
    assign a recordset to the ``records`` variable. Context exposed:
    ``env``, ``now``, ``today``, ``datetime``, ``date``, ``time``,
    ``timedelta``, ``relativedelta``. Invalid code or domains resolve
    to an empty recordset rather than raising.

- **Agent Max Records Per Fire** — caps a per-record fire to the first
  N resolved records (default ``100``; ``0`` means no cap).
- **Agent Prompt** — the initial user message sent to the agent,
  rendered as an inline template (see placeholders below).
- **Agent Chain Strategy** — ``Per Record`` links each new session to
  the most recent prior session for the same
  (``action_server_id``, ``res_model``, ``res_id``) tuple via
  ``previous_session_id``; ``None`` disables chaining.
- **Caps** — four per-action hard limits (see below).

When the action runs, the dispatcher first honours any records already
in the evaluation context (the ``records`` / ``record`` passed by a
contextual action or automation rule, or the ``active_ids`` /
``active_id`` in context). Only when no records are supplied does it
fall back to the configured domain or Python source. In single mode it
spawns one session over the whole recordset; in per-record mode it
spawns one session per record (capped by *Max Records Per Fire*). Each
session is created and ``start()``-ed as the action's author
(``create_uid``); a failed ``start()`` lands the session in the
``error`` state with the message rather than bubbling up.

When that author is archived the fire is refused with an error instead
of running under another identity — archiving a user is how an
administrator revokes their access, so their stored prompts must not
keep running with rights they never had. Re-create the action under an
active user to resume it. Actions shipped as module data are authored
by the superuser, which denotes no person: those run as the
administrator, never wider than the author's own rights.

Prompt template placeholders
----------------------------

The agent prompt is rendered with Odoo's inline-template engine
(``{{ ... }}`` expressions). Available variables:

- ``{{ user }}`` — the current user.
- ``{{ company }}`` — the active company.
- ``{{ env }}`` — the full Odoo environment for ad-hoc lookups.
- ``{{ ctx }}`` — the action's context dictionary.
- ``{{ today }}`` — ISO date string.
- ``{{ record }}`` — per-record mode: the current record. Empty recordset
  in single mode.
- ``{{ records }}`` — single mode: the resolved recordset. Empty
  recordset in per-record mode.
- ``{{ previous_session }}`` — a read-only proxy over the prior session
  in the chain. ``previous_session.last_text`` returns the prior
  assistant reply; ``previous_session.tool_log`` returns a list of
  ``{name, arguments, output}`` dicts. Empty proxy when chaining is
  off or on the first run.

If rendering raises, the dispatcher falls back to the raw prompt and
records a ``prompt_render_error`` event on the spawned session, so a
broken template never silently swallows a fire.

Per-record dispatch and chaining
================================

In ``Per Record`` mode the action resolves its recordset on every fire
and creates one session per record (capped by *Max Records Per Fire*).
Each spawned session carries:

- ``action_server_id`` — the source server action.
- ``res_model`` / ``res_id`` — the dispatched record. The session
  posts an internal note to that record's chatter with a back-link to
  the session form, so every AI run a record spawned stays visible
  from the record.
- ``previous_session_id`` — when *Agent Chain Strategy* is
  ``Per Record``, the most recent prior session for the same action
  and record; unset on the first run. The previous-session proxy lets
  a recurring agent prompt itself with
  ``Last time you said: {{ previous_session.last_text }}`` and see only
  the necessary text, not a full transcript.

Caps
====

Every spawned session is bounded by four limits configured on the
action, each falling back to a module-wide default when left at ``0``:

.. list-table::
   :header-rows: 1
   :widths: 30 15 55

   * - Field
     - Default
     - Bounds
   * - ``agent_max_resumes``
     - ``50``
     - total resumes / recurring fires of a session
   * - ``agent_max_lifetime_hours``
     - ``720`` (30d)
     - wall-clock since the session was created
   * - ``agent_max_total_tokens``
     - ``1000000``
     - combined input + output tokens
   * - ``agent_max_cost_eur``
     - ``5.00``
     - accumulated session cost in EUR

``_agent_effective_caps()`` resolves the per-action value or the
default. The caps are read back when a session resumes through **MuK
AI Schedule**; install it alongside if you need them enforced.

Firing from automation rules and crons
=======================================

Because ``ai_agent`` is a normal server-action state, three trigger
paths come for free:

1. **Contextual / manual actions** — run the server action against a
   selection on a list or a single form record; the selected records
   flow straight into the dispatcher.
2. **base.automation rules** — point a rule's server action at an
   ``ai_agent`` action to fire an agent on create / write / unlink /
   time-based triggers. The session exposes the originating rule via
   the related ``base_automation_id``. *MuK AI > AI Automation Rules*
   lists every rule wired this way.
3. **ir.cron scheduled actions** — attach a scheduled action to an
   ``ai_agent`` server action to fire an agent on a cadence. *MuK AI >
   AI Scheduled Actions* lists every cron wired this way.

Seeing the sessions on the record
=================================

Per-record dispatch writes ``res_model`` / ``res_id`` on every session
it spawns, which is what **MuK AI Chatter** builds on: it posts the
note back-linking to the session, lists the runs in an *AI Sessions*
box in that record's chatter, collects them in the *Records* space,
and grants a non-admin read access to a linked session only when they
can read the underlying business record. See that module's
documentation.

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
