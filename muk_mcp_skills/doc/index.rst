==============
MuK MCP Skills
==============

Implements the Skills extension of the Model Context Protocol on top of the
MuK MCP Server. Administrators write skills in Odoo: a name, a line that tells
the AI client when to use it, the instructions and the files they refer to.
Every MCP client that supports the extension lists the skills the user of its
key may use and loads one when a request fits.

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

Skills are managed under *Settings > MCP > Catalog > Skills*, and
*Settings > General Settings > MCP Extensions* links to them with *Manage
Skills*. Only administrators can change them. A skill has:

- *Name*: the identifier clients list and call it by. Lowercase letters,
  digits and single hyphens, 64 characters at most.
- *Description*: what the skill does and when to use it, 1024 characters at
  most. It is all a client reads before it decides to load the skill.
- *Groups*: the groups the skill is served to. Without one it is served to
  every user.
- *Instructions*: the markdown the client follows.
- *Files*: documents, templates or images next to the instructions. Mention
  one by its name; the client reads it when it needs it. The files of a skill
  may hold 16 MB, and clients may accept less.

Archive a skill to stop serving it.

Usage
=====

Connect a client with *Settings > MCP > Connect*. A client that supports the
Skills extension and the protocol revision ``2026-07-28`` needs nothing else.

- **Claude Code** lists the skills after ``/`` as ``<server>:<skill>``, for
  example ``/odoo:quote-follow-up``, and loads one by itself when a request
  fits its description. It asks before it loads a skill unless you allowed
  that version.
- **Claude** and other clients that support the extension list the skills of a
  connected server in their own way.

A skill is served with the rights of the user the key belongs to. Its
instructions work with the tools of the server, so the access rights of that
user and the scope of the key apply to everything a skill does.

Every file is listed with its size and SHA-256 digest. A changed skill gets a
new digest, and a client asks for a new approval before it uses it.

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
