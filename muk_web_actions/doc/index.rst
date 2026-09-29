=================
MuK Batch Actions
=================

Runs server actions and reports from the Actions and Print menus in batches
instead of in one request. A server action set to Execute in Batch processes the
selected records in slices of a configurable size, and a report set to Execute in
Batch downloads one file per record, both behind a progress bar. Each batch is its
own transaction, so large selections stay below the server timeout and a failing
batch keeps the batches before it saved.

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

Batching is set per action, in debug mode:

- **Server actions** (Settings > Technical > Server Actions): turn on
  *Execute in Batch* and set the *Batch Size*, the number of records sent to the
  server per request. Such an action should not return an action to open, as
  it runs once per batch.
- **Reports** (Settings > Technical > Reports): turn on *Execute in Batch* on a
  PDF or text report. HTML reports cannot be batched.

The action or report has to be in the Actions or Print menu of its model
(*Create Contextual Action* or *Add to the 'Print' menu*).

Usage
=====

1. Select records in a list or kanban view, or open a single record, and pick
   the action from the Actions menu or the report from the Print menu.
2. A progress bar shows the current batch and the estimated time left. Server
   actions run in slices of the batch size; reports download one file per
   record.
3. When all records of the domain are selected, the ids are resolved on the
   server first, up to the active ids limit.
4. If a batch fails, the run stops with the error; the batches before it stay
   saved.

Actions and reports without the flag keep the standard behaviour.

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
