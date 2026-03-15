==============
MuK MCP Server
==============

Implements a native MCP (Model Context Protocol) server inside Odoo,
exposing business data and operations to any MCP-compatible AI client
such as Claude Desktop, Claude Code, Cursor, Windsurf, or Codex CLI.

Installation
============

To install this module, you need to:

Download the module and add it to your Odoo addons folder. Afterward, log on to
your Odoo server and go to the Apps menu. Trigger the debug mode and update the
list by clicking on the "Update Apps List" link. Now install the module by
clicking on the install button.

Upgrade
============

To upgrade this module, you need to:

Download the module and add it to your Odoo addons folder. Restart the server
and log on to your Odoo server. Select the Apps menu and upgrade the module by
clicking on the upgrade button.

Configuration
=============

After installation, go to **Settings > General Settings > MCP Server** to
enable or disable the server and configure the session timeout.

Authentication is handled via Odoo API keys (Bearer tokens) or, if the
MuK REST API module is installed, via Basic Auth, OAuth1, or OAuth2.

Usage
=====

The MCP server is available at the ``/mcp`` endpoint. Any MCP-compatible
client can connect to it using the Streamable HTTP transport.

**Example: Claude Code**

.. code-block:: bash

    claude mcp add-json odoo '{"type":"url","url":"http://localhost:8069/mcp"}'

**Built-in Tools**

The module ships with 9 built-in tools:

- ``list_models`` — List available Odoo models
- ``get_model_schema`` — Get field definitions for a model
- ``search_read`` — Search and read records
- ``read_record`` — Read specific records by ID
- ``search_count`` — Count records matching a domain
- ``create_record`` — Create a new record
- ``update_record`` — Update existing records
- ``delete_record`` — Delete records
- ``execute_method`` — Call a public method on a model

All tools are manageable via the **MCP Server > Tools** menu in the backend.

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
