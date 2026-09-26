=============
MuK Tree List
=============

The module adds the treelist view type: a list view whose rows nest under their
parent record and open and close like the folders of a file explorer. It works
on any model with a many2one to itself, such as product categories, contacts,
departments or locations, and keeps what a list view offers: inline editing,
optional columns, sums, widgets and decorations.

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

No configuration is required for users. A developer adds a treelist to an
action by writing a view with the ``treelist`` tag and adding ``treelist`` to
the action's view mode. The view takes the same children and attributes as a
``list``, plus the ones below.

.. code-block:: xml

    <treelist parent_field="parent_id" editable="bottom" draggable="1">
        <field name="name"/>
        <field name="budget" sum="Total" rollup="1"/>
    </treelist>

* ``parent_field`` - the many2one to the same model, ``parent_id`` by default.
* ``expand="1"`` - open every row when the view is first loaded.
* ``draggable="1"`` - move a record under another one by drag and drop.
* ``widget="handle"`` on a sequence field - drag a row above or below one of
  its siblings to change their order, as in a list.
* ``rollup="1"`` on a numeric field without a widget - show the total of the
  subtree on each parent row and in the footer.
* A ``<column>`` as the first column - its fields sit side by side after the
  chevron, such as an icon before the name. Give it a ``width`` such as
  ``[240]``: a list sizes a column group by its first field.

Usage
=====

* Only the top-level records are paged. Click the chevron of a row to load and
  show its children; the open rows are remembered per action in the browser.
  A row with more children than the page size gets its own pager, like a group
  of a list, to page through them.
* Right opens the focused row, Left closes it or jumps to its parent.
* A search shows every match in place, below all of its parents up to the
  root. The parents that do not match are shown greyed out and opened
  automatically; they cannot be selected and are left out of the sums. A
  record whose parent is archived, not readable or outside the domain of the
  action is shown as a root instead.
* Click *+* on a row to add a child directly under it, with the parent already
  filled in; Enter saves it and starts the next sibling. Without ``editable``
  the form opens instead.
* Drag a row by its handle onto another row to move it under that row, or onto
  the upper or lower edge of a row to make it a sibling. The future parent is
  highlighted while dragging. A record cannot be moved under one of its own
  children.
* Grouped, each group shows its records as a tree and pages its top-level rows.
  A record whose parent falls into another group is a root of its own group.
  A search inside groups shows only the matches, without greyed-out parents.
* A search panel that the list view shows is shown next to the tree as well.
* An Excel export lists every parent before its children, indents the first
  column by level and outlines the rows, so they open and close in Excel too.
  During a search, the greyed-out parents are exported as header rows above
  their matches, as on the screen.
* *Expand All* and *Collapse All* in the cog menu open or close every row, or
  the groups when the view is grouped.

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
