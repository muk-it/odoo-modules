=============
MuK AI Skills
=============

Adds skill records to MuK AI Assistant that bundle a name, a one-line
description the agent reads to decide when to use it, a markdown body of
instructions and attached resource files. Every skill a chat may use is listed
in the agent's instructions, so it can pick one by itself, and users run them
from the skills menu of the chat composer or with a ``/<name>`` command.

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

Skills are managed under *MuK AI > Skills*, also reached from *Manage AI
Skills* in the MuK AI settings. A skill has:

- **Label** and **Technical Name**: the name shown in the chat, and the
  lowercase identifier that is also its ``/<name>`` command.
- **Icon**: a Material Symbol picked from a grid, shown in the skills menu.
- **Description**: one line the agent reads to decide when the skill applies.
- **Body**: the instructions in markdown. Every change is kept under
  *Body History*, where an earlier revision can be restored. The body reaches
  the agent as plain text and is never rendered as a template.
- **Resources**: attached files. The agent receives an ``odoo://attachment/<id>``
  uri for each and reads one with ``read_resource`` when the task needs it.
- **Available** and **Models**: whether the skill works anywhere or needs a
  record or a list, a single record, or a record with a chatter open, and the
  models it is limited to.
- **Visibility** and **Agents**: *Only Me*, *Selected Users* or *Everyone*,
  and the agents that may use it. Only the owner and administrators can edit
  a skill. Scheduled and automated chats see the skills of the user they run
  as.

The module ships the ``reply`` skill, which drafts a chatter reply and opens
the mail composer with the draft.

Usage
=====

In a chat, ask as usual: the agent calls a skill itself when the request
matches its description. To run one directly, click the lightning button next
to the paperclip and pick it from the menu, which lists recently used skills
first, or type ``/`` to see the skills next to the built-in commands. Text
after the name, as in ``/reply thank them for the quick delivery``, is passed
along with the skill.

A skill that needs something open is greyed out under *Once something is
open*, with what it needs, until the chat has a fitting record or list, and
the server refuses it as well.

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
