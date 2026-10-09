==============
MuK AI Chatter
==============

Lets users mention an agent of MuK AI Assistant with the regular ``@`` syntax
in a Discuss channel or a direct chat, and posts its answer in that
conversation, without the agent ever joining it or being mailed. In the
chatter of any record, a writing helper fixes, rewrites or drafts the message
being written. Chats linked to a record are listed in its chatter and
collected in a Records space.

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

Every agent gets an archived contact without an email address, which stands
in for it in conversations and stays out of the address book and every
contact picker. The **Chatter** group of the agent form under *MuK AI >
Agents* holds:

- **Answer Mentions**: whether colleagues can mention the agent. On by
  default; turned off, the agent is offered nowhere.
- **Agent Contact**: the contact standing in for the agent.

A mentioned agent runs the tools it carries, writes included, and never
stops to ask for an approval. Give an agent that people may mention only the
tools you mean it to use there.

The buttons of the writing helper are skills of the type *Composer* under
*MuK AI > Skills*. Each carries a **Category** that decides where it is
offered: *Fix*, *Rewrite* and *Transform* act on what is written, *Generate*
writes from the record. Reword them, add your own, or archive the ones your
team does not use. The *Chatter* space can name the agent the helper runs
under; otherwise the default agent answers.

Usage
=====

In a Discuss channel or a direct chat, type ``@``, pick the agent and write
the request. A short note answers at once and is replaced by the answer when
the run ends; record references in it become links, and *View the run* opens
the session with every step. A message written by an agent, or posted by a
tool of a running session, summons nobody. A record's chatter offers no
agents.

In a chatter composer, the AI button opens the writing helper. With text
selected it rewrites that part and shows the change as a diff; with a draft
it reworks the whole message; with nothing written it offers a reply, a
follow-up or a summary of the thread, with a length and a tone. Nothing
reaches the message until it is accepted. An instruction typed into the
helper can be saved as a quick action. *Continue in the AI chat* hands the
session to a chat window, whose *Use this* button puts an answer back into
the message. The full composer offers the same helper in its toolbar, as a
``/`` command, and behind the button in its footer.

A chat started for a record leaves a note on it and appears under the *AI
Sessions* button of its chatter, with a dot for its state. Users see the
runs they started; administrators see all of them.

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
