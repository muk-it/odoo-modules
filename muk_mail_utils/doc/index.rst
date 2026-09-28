==============
MuK Mail Utils
==============

Technical module to provide some utility features and libraries that can be used
in other applications. It adds a ``message_list`` list view with a preview pane
for the selected message, and a *Canned Response* command in the HTML editor.

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

No configuration required.

Usage
=====

* **Message preview**: other modules open message lists with
  ``js_class="message_list"``. Clicking a row, or moving to it with the keyboard,
  shows its author, recipients, attachments and body on the right. The pane
  appears on extra-large screens.
* **Canned responses**: type ``/`` in any HTML field, including the full email
  composer, pick *Canned Response*, search, and press Enter to insert it.

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
