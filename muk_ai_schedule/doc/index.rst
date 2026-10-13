===============
MuK AI Schedule
===============

Gives every MuK AI chat a wait tool. An agent pauses itself until a time,
until a record reaches a state or until a message is posted on a record, and
carries on by itself when that happens, with the note it left for itself.
Conditions are checked without calling the model, every wait has a timeout,
and the chat shows what it waits for with a button to wake it at once.

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

Open MuK AI > Settings and set Max waits per chat in the Limits block: how
often one chat may pause itself before it has to finish. Every wake-up runs
within the turn limits set there as well.

Usage
=====

Every chat offers the agent the wait tool. Ask for something that needs a
pause, for example "remind Acme about the invoice and wait for their reply".
The agent waits:

- until a time, given in seconds or as a date and time;
- until a record matches a condition, checked every minute;
- until a message or an email is posted on a record;
- in the last two cases, at most until the time it gave.

While it waits, the chat shows what it waits for and the note the agent left
itself, with Wake now and Stop. Typing a message wakes it too. When the chat
wakes, the agent learns why (time, timeout, record ready, message with its
text, record deleted, woken by hand) and goes on from there. To keep watch,
it checks, reports and waits again until the outcome is there.

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
