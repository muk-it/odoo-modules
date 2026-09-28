================
MuK Mail Routing
================

This module collects incoming emails that matched no alias and no thread, and
lists them as Lost Emails instead of letting them bounce. From there each email
is routed to a new or an existing record, and predefined routers turn one into,
for example, a new CRM lead in a single click. Outgoing emails that could not be
sent are listed as Failed Emails.

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

Go to *Discuss > Configuration > Routers* to create a router. A router names the
target model and whether an email creates a new record or is attached to an
existing one. For new records, a short Python snippet fills the fields from the
email; the default takes the subject as the name and the sender as the email.

Usage
=====

Open *Discuss > Lost Emails*. Selecting an email shows it in the preview on the
right. *Route* attaches the selected emails to any record you pick, and each
router adds its own button, such as *Create Lead*. *Discuss > Failed Emails*
lists the outgoing emails that could not be sent.

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
