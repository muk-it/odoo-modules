=============
MuK Web Utils
=============

Technical module to provide some utility features and libraries that can be used
in other applications. It adds field widgets and view options for other modules
to use, a setting to disable quick create on many2one fields, a Reports entry in
the debug menu, and fixes for the domain field and the tour pointer.

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

In debug mode, Settings > General Settings > Permissions offers the option to
disable quick create for many2one fields.

Usage
=====

Other modules use the widgets ``selection_icons``, ``text_icon`` and
``module_link``, the field options ``prettify`` (json) and ``no_open`` (one2many,
many2many), the ``icon`` attribute on list columns, the ``multi_actions`` client
action, the ``block_progress`` service and the Python helpers in ``tools``.

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
