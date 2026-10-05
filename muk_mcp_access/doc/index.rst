==============
MuK MCP Access
==============

Controls which Odoo models AI agents can reach through the MuK MCP Server,
independent of the user's normal access rights. Administrators build an
allowlist of models and choose read-only or read and write access per model,
optionally limited to the records matching a domain. While the list is empty
every model stays reachable; once it holds an entry, only the listed models
are exposed and the agent cannot discover or query anything else.

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

The allowlist lives under *Settings > MCP > Authentication > Access*, and
*Settings > General Settings > MCP Server* links to it with *Manage Model
Access*. Only administrators can change it.

- **Empty list**: every model is reachable through MCP, as without the module.
- **At least one entry**: only the listed models are reachable.

Each entry sets:

- *Read*: the model shows in ``list_models`` and the read tools
  (``search_read``, ``read_records``, ``describe_model``, ``export_records``,
  ``print_report``, ...) accept it.
- *Write*: the write tools (``create_records``, ``update_records``,
  ``delete_records``, ``call_method``, ...) accept it.
- *Record Domain*: an optional filter, like a record rule. Only records
  matching it are read, written, exported, printed or returned. It is
  evaluated with ``user``, ``company_id``, ``company_ids`` and ``time`` in
  scope, for example ``[('user_id', '=', user.id)]``.

*Add Models* in the list opens a wizard that adds several models at once with
the same permissions; it leaves out transient models and models already
listed. Archive an entry to switch it off without losing it.

Usage
=====

Once the allowlist holds an entry, every MCP call is checked against it:

- A tool that names a model raises an access error when the model is not
  listed or the tool's category, read or write, is not allowed for it.
- ``list_models`` returns only the models listed for reading, so an agent
  cannot discover the others.
- A record domain is merged into every search and checked for every record id
  a tool receives. A model-level ``call_method`` gets the domain merged into
  its ``domain`` argument, and a call that returns a record outside it is
  rolled back.
- ``odoo://`` resources are checked against the model and the record they
  belong to. Attachments linked to no record stay readable.

The check works on top of the MCP key's scope and the user's access rights:
it narrows what an agent reaches and never widens it.

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
