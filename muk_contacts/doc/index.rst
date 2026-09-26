============
MuK Contacts
============

This module improves and extends the contact app and the related partner model.
Companies and persons get a contact number from a sequence, a partner can name
its default invoice and delivery address, and the contact list shows more of
each contact. The contacts can also be browsed as a tree, with people and
addresses nested under their company.

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

The contact number automation is switched on in Settings, in the Contacts
block. While it is on, every new company or person without a parent draws the
next number from the Contact Number sequence; its people and addresses share
it. Configure Sequence below the switch opens the sequence, to change its
prefix, padding or next number.

Usage
=====

The contact number sits above the address on the contact form. A contact
without one gets one with the button beside the field. The number can be
searched wherever a contact is searched.

The Company switch above the job position tells a top-level contact apart
as a company or a person. Odoo sets it from the tax ID, and it can be changed
by hand until the tax ID changes again; a contact that belongs to a company is
always a person. The search
filters Persons and Companies list either kind.

The default invoice and delivery address are set on the Sales & Purchase tab
and are used by sales orders instead of the first matching address.

The contact list adds the contact number, the company, the address type, the
internal notes and the kind of user as optional columns, and the search adds
filters for main contacts, portal users and internal users. The tree list view
in the contacts app shows each company with its people and addresses nested
beneath it; drag a contact onto another company to move it there.

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
