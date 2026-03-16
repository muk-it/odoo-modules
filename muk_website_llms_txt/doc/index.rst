==========================
MuK LLMs.txt & Markdown
==========================

Make your Odoo website AI-ready by implementing the llms.txt standard
and Cloudflare-style markdown content negotiation. AI agents and crawlers
can discover your content via /llms.txt and request any page as clean
markdown via the HTTP Accept header.

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

After installation, navigate to Website > Configuration > Settings. Under the
"AI & Agents" section you can configure:

- **LLMs.txt**: Enable or disable the /llms.txt endpoint.
- **LLMs Full**: Enable or disable the /llms-full.txt endpoint.
- **Content Signal Policy**: Control how AI may use your content.
- **Content Sources**: Choose which content types to include (pages, blogs, products, events).

Usage
=============

Once installed and enabled, your website will automatically serve:

- ``/llms.txt`` -- A structured index of all published content following the
  llms.txt standard (llmstxt.org).
- ``/llms-full.txt`` -- Full markdown content of all published pages for deep
  AI ingestion.
- Any page responds with clean markdown when an AI agent sends
  ``Accept: text/markdown`` in the HTTP request.

Response headers include ``x-markdown-tokens`` (estimated token count) and
``Content-Signal`` (AI usage policy).

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
