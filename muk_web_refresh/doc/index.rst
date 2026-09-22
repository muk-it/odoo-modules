============
MuK Refresh
============

Adds a refresh button next to the pager so the current view can be reloaded
without leaving it. A double-click on the button turns on auto refresh, which
reloads a list or kanban view at a fixed interval and pauses while the browser
tab is in the background. A Reload Views server action lets an automation rule
push a refresh to every open view of a model from the backend.

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

The auto refresh interval is read from the system parameter
``muk_web_refresh.pager_autoload_interval``, in milliseconds. It defaults to
30000 and is set under Settings > Technical > System Parameters.

Usage
=====

1. Open any backend view and click the refresh button left of the pager to
   reload it once.
2. Double-click the button on a list or kanban view to turn auto refresh on.
   A countdown appears next to the button and the choice is remembered per
   view. Double-click again to turn it off.
3. To refresh from the backend, create an automation rule under Settings >
   Technical > Automation Rules, pick the model and the trigger, and add a
   *Reload Views* action. Leave *View Types* empty to reload every view type,
   or list the ones to reload, for example ``list, kanban``.

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
