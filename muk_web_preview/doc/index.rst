===========
MuK Preview
===========

Extends the built-in file viewer with additional preview support for file types
such as email messages, CSV files, and Microsoft Office documents. The module
also adds common text-based mimetypes to the viewer so they can be previewed
directly without downloading.

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

To enable Microsoft Office file preview, go to Settings and enable the
**MS Office Preview** option. This uses the Microsoft Office Online viewer
to render docx, xlsx, and pptx files directly in the browser. The Odoo
instance must be publicly accessible from the internet for this feature
to work. Files are served via short-lived one-time token URLs for security.

Usage
=============

Once installed, the file viewer automatically supports additional file types:

- **Email Messages (.eml):** Email files are rendered as HTML with inline images
  resolved from CID attachments.

- **CSV/TSV Files:** Comma and tab separated files are displayed as formatted
  HTML tables with headers, striped rows, and truncation for large files.

- **Microsoft Office (.docx, .xlsx, .pptx):** Office documents are previewed
  using the Microsoft Office Online viewer in read-only mode. A "Preview only"
  badge is shown to make it clear the file cannot be edited. This feature must
  be enabled in Settings and requires the Odoo instance to be publicly
  accessible.

- **Additional Text Types:** Files with mimetypes such as ``text/csv``,
  ``text/markdown``, ``text/xml``, ``text/x-python``, ``text/x-rst``,
  ``text/x-yaml``, ``application/xml``, ``application/x-yaml``,
  ``application/x-sh``, and ``application/sql`` can now be previewed
  directly in the file viewer.

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
