==============
MuK AI Product
==============

Adds a Product Content Writer to MuK AI Assistant that adds products from web
links and vendor price lists, ready to purchase, and has skills for the product
form: find the facts of a product in its own data, its documents and on the
web, from the manufacturer's page or datasheet, write its name and
descriptions from those facts only, translate them into every language the
company sells in, and add image variants as extra images marked as
AI-generated. Every change waits for approval in the chat. Web shop and search
texts are filled when eCommerce is installed; barcodes and manufacturer data
are never generated.

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

An AI provider with a chat model has to be set up in MuK AI, and an image
model for the image variants, and web search for the agent to look products
up. Price lists of more than a few rows need a provider whose code sandbox
reads the files of the chat: OpenAI, Anthropic or Google. The texts are written in every active language.

With the eCommerce app the writer also fills the web shop description and the
search texts, and adds images as extra images of the product.

Usage
=====

Open a product and start a chat on it. Switch to the **Product Content
Writer** (``/agent``) and pick one of its suggestions, or type ``/`` to pick a
skill. The skills run with the General Assistant and with the Product Content
Writer:

* **Complete the Product** finds the facts of the product: in a document
  attached to it or to the chat, on its manufacturer page, or with a web
  search by its manufacturer code, barcode or name. Without a source it asks
  you for a datasheet or a few details, or writes from what is entered only.
  It then writes the texts from those facts in every product language and
  offers image variants.
* **Product Images** generates variants and adds the ones you pick as extra
  images.
* **Add Products** works anywhere: send a link to a web shop or supplier page,
  or attach a price list (Excel, CSV or PDF). It finds or creates the vendor,
  matches each item against your products by the vendor's code, the barcode
  or the reference, shows what is new and which prices change, and then
  creates the products with their vendor price and image, or updates the
  price. Long lists are read in the code sandbox of the AI provider (OpenAI,
  Anthropic or Google). Approve the first product with **Allow for
  session** to add the rest of the list in one go.

Translating a product or rewriting a description is a plain chat request to
the writer.

Every write shows its changes for approval first, one language at a time,
starting with English, the language the others fall back to.

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
