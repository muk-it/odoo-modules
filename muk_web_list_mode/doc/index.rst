=============
MuK List Mode
=============

Enables you to switch between read and editable list views as long as the user
has the needed access rights and the list view does not explicitly disable edit
mode by being set to readonly.

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

On any list view the user is allowed to edit, a button group next to the pager
switches the mode. With "Open Form View" a click on a row opens the record in
its form. With "Inline Edit Mode" the rows are edited directly in the list;
select several rows to change a field on all of them at once. The chosen mode
is remembered per user, action and model. The switch is hidden in dialogs and
on small screens.

The lists of one2many and many2many fields in a form carry a toggle in the
last column of their header, next to the optional columns. It shows the
current mode and switches to the other one on click: "Open Form View" opens a
line in a dialog, "Inline Edit Mode" edits it in the row, and "Add a line"
follows the mode. The default is the mode set on the field's list; the chosen
mode is remembered per user, model and field.

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
