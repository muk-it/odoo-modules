==============
MuK MCP Access
==============

Model-level access control for the MuK MCP Server. Restricts which Odoo
models AI agents can discover and operate on through the Model Context
Protocol, independent of the user's normal access rights.

Requires `MuK MCP Server <https://apps.odoo.com/apps/modules/17.0/muk_mcp>`_.

Installation
============

To install this module, you need to:

Download the module and add it to your Odoo addons folder. Afterward,
log on to your Odoo server and go to the Apps menu. Trigger the debug
mode and update the list by clicking on the "Update Apps List" link.
Now install the module by clicking on the install button.

Upgrade
=======

To upgrade this module, you need to:

Download the module and add it to your Odoo addons folder. Restart the
server and log on to your Odoo server. Select the Apps menu and upgrade
the module by clicking on the upgrade button.

Configuration
=============

Navigate to *Settings > MCP > Model Access* to manage the whitelist.

- **Empty list** — every model is accessible (backwards-compatible
  default).
- **Non-empty list** — only listed models are exposed to MCP clients.

Each entry controls:

- **Read** — model is visible in ``list_models`` and queryable via
  ``search_read``, ``read_records``, ``describe_model``, etc.
- **Write** — model is writable via ``create_records``,
  ``update_records``, ``delete_records``, and ``call_method``.

Use the *Add Models* button to bulk-enable multiple models at once.
The wizard excludes transient models and models already in the
access list.

Usage
=====

Once the whitelist contains at least one entry, the module enforces
two restrictions:

1. **Tool-level blocking** — any tool that accepts a ``model``
   argument (``search_read``, ``create_records``, ``describe_model``,
   etc.) raises ``AccessError`` when the model is not in the
   whitelist or the operation is not allowed.

2. **Discovery filtering** — ``list_models`` only returns models
   that appear in the whitelist, so the AI client cannot discover
   restricted models.

The check respects the tool's category: read tools check
``allow_read``, write tools check ``allow_write``. This layering
works alongside MCP API key scopes (read-only keys, rate limits)
and Odoo's built-in record rules and model ACLs.

Credits
=======

Contributors
------------

* Mathias Markl <mathias.markl@mukit.at>

Author & Maintainer
-------------------

This module is maintained by the `MuK IT GmbH <https://www.mukit.at/>`_.

MuK IT is an Austrian company specialized in customizing and extending
Odoo. We develop custom solutions for your individual needs to help you
focus on your strength and expertise to grow your business.

If you want to get in touch please contact us via mail
(sale@mukit.at) or visit our website (https://mukit.at).
