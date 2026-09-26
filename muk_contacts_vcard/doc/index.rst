==================
MuK Contacts vCard
==================

This module extends the vCard export to include more detailed contact
information and improves the contact form. People get a first, middle and last
name, honorific titles, a gender, a birthdate, a nickname, a mobile number and
a private email and phone, and the vCard download writes all of them to the
properties an address book reads.

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

The honorific titles are managed under Contacts > Configuration > Contact
Honorifics. Each title has a full name, an abbreviation, a position before or
after the name and a sequence that orders several titles on one contact.

Usage
=====

A person, a contact that is not a company, has a first, middle and last
name instead of a single name field; the name is built from the parts. On
install, the existing names are split into their parts. The Personal
Information section holds the gender, the honorific prefixes and suffixes, the
nickname, the birthdate and a private email and phone. The mobile number sits
next to the phone and is found by the phone search.

To download a vCard, open a contact and choose Download (vCard) in the action
menu, or select several contacts in the list to download them together.

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
