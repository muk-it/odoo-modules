================
MuK AI Subagents
================

Lets an agent hand focused tasks to other agents and wait for their reports.
Each subagent runs as a chat of its own, in parallel, with its own agent
configuration and never with more rights than the chat that started it. One
live card in the conversation shows what every subagent is doing, takes an
approval or an answer in place, and folds into the reports once the run ends.

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

Open MuK AI > Agents and pick the agent that should coordinate. Switch on
Allow Delegation and list the agents it may hand tasks to under Delegates; the
agent is then offered the delegate tool and told whom it may use. Its
Delegation tab says, in plain words, when it hands work to them; the text
starts with a sensible default and can be adapted per agent. A subagent
keeps its own tools, model and approval mode, but asks for approval whenever
the chat that started it would, stays read-only when that chat is, and only
gets the tools the coordinating agent may use itself.

Each subagent's turn keeps to the Turn Cost Limit under Settings > MuK AI >
Limits, like any chat. Subagents run on the MuK AI session workers, so the
server needs its cron workers running.

Usage
=====

Ask the coordinating agent for work with independent parts. When it
delegates, a card in the conversation lists its subagents, the ones waiting
for you first: what each one does right now, how long it has been running,
and once it ended, its report. A subagent that needs an approval or an answer
shows its question in the card; answer it there. While subagents work, the
card sits above the message box, with the finished ones hidden behind Show
finished, and the transcript keeps their reports. Open chat shows a subagent's
own conversation, where a message gives it direction for its next step. Stop
ends one subagent, Stop all ends every one still running, and the chat goes on
with what they reported.

The coordinating agent manages its subagents too. Its subagents run in the
background while it keeps answering you, the reports reaching it as each
subagent ends, even after its turn; when it needs the results first, it waits
for them. It can check on its subagents and read their last
messages, give a running one new direction, let one that ended, failed or was
stopped carry on with everything it did so far, and stop one.

A subagent that keeps making the same call with the same result is warned,
and stopped if it goes on. Every subagent that ends says why: done, stopped,
at the budget, at the round limit, or for repeating itself.

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
