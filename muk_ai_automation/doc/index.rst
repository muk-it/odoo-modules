=================
MuK AI Automation
=================

Extends MuK AI with a server action of type Run AI Agent, so administrators
can run an AI agent from any server action, automation rule or scheduled
action. It starts one chat for all target records or one per record, selected
by the trigger, a domain or Python code, and lets each chat recall the
previous run for the same record.

Installation
============

To install this module, you need to:

Download the module and add it to your Odoo addons folder. Afterward, log on to
your Odoo server and go to the Apps menu. Trigger the debug mode and update the
list by clicking on the "Update Apps List" link. Now install the module by
clicking on the install button.

Upgrade
=======

To upgrade this module, you need to:

Download the module and add it to your Odoo addons folder. Restart the server
and log on to your Odoo server. Select the Apps menu and upgrade the module by
clicking on the upgrade button.

Configuration
=============

Install the module from the Apps menu.
MuK AI > Automation holds three lists, for administrators: Agent Actions,
the Automation Rules and the Scheduled Actions that run an agent. Their forms
show only what an agent needs, and what is created there runs an agent.

An agent action is a server action of type Run AI Agent:

* **Agent**: the agent that does the work, with its model, tools and approval
  mode.
* **Dispatch**: One Chat hands all target records to a single chat; One Chat
  per Record starts a chat for each record, linked to it.
* **Memory**: with one chat per record, Continue per Record hands each chat
  the previous chat of this action for the same record.
* **Record Limit**: with one chat per record, the most chats one run starts.
  Zero means no limit.
* **Records**: a scheduled action takes its records from a Domain built in
  the domain editor or from Python Code that assigns a recordset to
  ``records``. The code is checked when the action is saved. An agent action
  runs on the records selected in a list, and an automation rule on the
  records that triggered it.
* **Prompt**: the message sent to the agent, an inline template. Write a value
  as ``{{ expression }}`` with ``record`` (one chat per record), ``records``
  (one chat for all), ``previous_session.last_text`` and
  ``previous_session.tool_log`` (the last answer and the tool calls of the
  previous chat, when the action continues per record), ``user``,
  ``company``, ``env`` and ``today``. The Help tab of the action lists them.

Chats run on the MuK AI session workers, so the server needs its cron workers
running.

Usage
=====

Create Contextual Action adds an agent action to the Actions menu of its
model: select records in the list and run it from there; the notification
says how many chats it started. In an automation rule, add an action of type Run AI Agent
and it runs on the records that triggered the rule. A scheduled action of
type Run AI Agent runs at its interval on the records of its domain or code,
and Run Manually starts it at once.

The AI Chats button of an agent action lists the chats it started, with their
state, cost and answer; MuK AI > Reports > Sessions lists them with all other
chats. A chat started for one record is linked to it: a note in the record's
chatter links to the chat, and its AI Sessions button lists every run for the
record.

In the chat sidebar, the chats of agent actions and automation rules are
listed under the Automation space, and those of scheduled actions under
Scheduled. Set Space on an action to list its chats in a system space of
your own instead.

Each chat runs with the access rights of a user: a run from the Actions menu
or the Run button as the user who starts it, a scheduled action as its
Scheduler User, and an automation rule as its Run Agents As user, whoever
triggers it. A chat finished by an action stays out of the unread chats; one
that stops with an error or waits for an answer is flagged. The superuser is
replaced by the administrator, and an archived user makes the action refuse to
run. A prompt that does not render fails its chat with the reason, and an
action whose agent is archived refuses to run.

Credits
=======

Contributors
------------

* Mathias Markl <mathias.markl@mukit.at>

Author & Maintainer
-------------------

This module is maintained by the `MuK IT GmbH <https://www.mukit.at/>`_.

MuK IT is an Austrian company specialized in customizing and extending Odoo.
We develop custom solutions for your individual needs to help you focus on
your strength and expertise to grow your business.

If you want to get in touch please contact us via mail
(sale@mukit.at) or visit our website (https://mukit.at).
