===========
MuK Preview
===========

Extends the file viewer and the attachment thumbnails with previews for
email files (.eml), Outlook messages (.msg), CSV and TSV tables and source
code. Remote images in emails stay blocked until they are loaded on demand.
Word, Excel and PowerPoint files can be opened with the Microsoft Office
Online viewer. Reports open from the print menu in the file viewer instead
of downloading, and downloaded reports can open in a new browser tab as well.

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

Emails, Outlook messages and tables need no configuration. To open Word,
Excel and PowerPoint files in the Microsoft Office Online viewer, enable
**MS Office Preview** under Settings > General Settings > Integrations.
Microsoft downloads the file through a signed link that expires after five
minutes, so the database must be reachable from the internet.

To open every downloaded PDF or text report in a new browser tab as well,
enable **Open Downloaded Reports** in the same section. The browser must
allow pop-ups for the database.

Usage
=====

Click an attachment anywhere in Odoo, for example in the chatter, and it
opens in the file viewer:

- **Email files (.eml)** and **Outlook messages (.msg)** show the sender,
  recipients, date, attachments and the body with its embedded pictures.
  Remote images are blocked; **Show remote images** loads them for that
  message.
- **CSV and TSV files** are shown as a table.
- **Source code and configuration files** are shown as text.

The chatter cards show a preview of these files before they are opened.

Every report in the **Print** menu has an eye icon. Clicking the icon shows
the report in the file viewer instead of downloading it; the download button
of the viewer saves it under its usual file name. On a phone the eye is not
shown, and a report is downloaded without opening a new tab.

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
