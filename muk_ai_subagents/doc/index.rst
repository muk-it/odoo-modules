================
MuK AI Subagents
================

Delegate work to focused subagents that run in parallel.

An agent can hand a task to another agent and carry on. Each subagent is
a session of its own, with its own context and its own agent
configuration, so the permission model is the one you already know.
One quiet line above the composer says what the subagents are doing,
every subagent is openable and keeps a permanent link, and a subagent that
starts repeating itself says so before it ends.

This addon plugs into ``muk_ai``'s session runtime via ``_inherit``
only — no fork of ``muk_ai`` or ``muk_mcp`` source.

Permissions
===========

A subagent is governed exactly like the main agent. ``Approval Mode``,
``Restrict to Read-only Tools`` and ``Tool Filter`` already live on
``muk_ai.agent`` and do all the work. Two rules hold on top: a subagent's
permissions are the intersection with the conversation that spawned
it, never the union; and no message from any agent counts as a human
approval.

A subagent that needs an approval or an answer raises it in the
conversation the user is actually in, labelled with the subagent's name.
Approving, allowing for that subagent's session, or rejecting all behave
as they do for the main agent — and rejecting one action lets the
subagent re-plan rather than ending the run.

Steering a running subagent
===========================

The user can change a subagent's direction while it works: open the
subagent and type into the one composer, which is already addressing it.
Nothing arrives mid-thought — a message is handed over at the end of the
step the subagent is on, so a tool call in flight always finishes.

A subagent that has already reported is asked again on a turn of its own
rather than steered, and at most five messages may wait for one subagent.
The main agent is told in its own transcript when the user redirects a
subagent, because it is waiting on a brief it wrote.

Limits
======

Five subagents at once per run, one level deep, a budget covering the
whole tree, and a subagent deadline that never outlives its parent's. At
a limit the delegation tool is withheld rather than offered and
refused.

Loop detection fingerprints each action as the tool, its arguments and
a hash of the result, so a repeated action with changing results is
left alone while a genuine loop is caught. Heartbeats flag a subagent
that goes quiet. Every ending carries a reason, and anything that is
not a clean finish is shown as a warning rather than buried in prose.

Installation
============

To install this module, you need to:

Download the module and add it to your Odoo addons folder. Afterward,
log on to your Odoo server and go to the Apps menu. Trigger the debug
mode and update the list by clicking on the "Update Apps List" link.
Now install the module by clicking on the install button. Requires
``muk_ai``.

Upgrade
=======

To upgrade this module, you need to:

Download the updated module and replace the folder in your Odoo addons
path. Restart the Odoo server, go to the Apps menu, find **MuK AI
Subagents** and click Upgrade.

Live provider tests
===================

A second suite talks to a real provider instead of a recorded payload. It is
excluded from every normal run — it costs money, needs the network and cannot
be deterministic — and is the only thing that proves the model reads the tool
description and uses it::

    odoo-bin -d <db> -u muk_ai_subagents --test-enable --test-tags muk_ai_live

It skips itself when the database has no provider key.

Credits
=======

Contributors
------------

* Mathias Markl <mathias.markl@mukit.at>

Author & Maintainer
-------------------

This module is maintained by MuK IT GmbH.

MuK IT is an Austrian company specialized in customizing and extending
Odoo. We develop custom solutions for your individual needs to help
you focus your resources on your core business.

For more information, please visit our `website <https://mukit.at>`_.
