# MuK Preview

[![Odoo 20.0](https://img.shields.io/badge/Odoo-20.0-714B67?style=flat-square)](https://apps.odoo.com/apps/modules/muk_web_preview)
![Community](https://img.shields.io/badge/CE-%E2%9C%93-1C3A4C?style=flat-square)
![Enterprise](https://img.shields.io/badge/EE-%E2%9C%93-33627E?style=flat-square)
![Odoo.sh](https://img.shields.io/badge/Odoo.sh-%E2%9C%93-1C3A4C?style=flat-square)
![On-Premise](https://img.shields.io/badge/On--Premise-%E2%9C%93-33627E?style=flat-square)
[![License LGPL v3](https://img.shields.io/badge/License-LGPL_v3-blue?style=flat-square)](LICENSE)
[![YouTube demo](https://img.shields.io/badge/YouTube-demo-FF0000?style=flat-square&logo=youtube&logoColor=white)](https://youtu.be/_EZG9yqAG7w)
[![Website mukit.at](https://img.shields.io/badge/Website-mukit.at-243742?style=flat-square)](https://www.mukit.at)

**Open the email, not the download folder.** Email files, Outlook messages and
CSV exports open in the Odoo file viewer and show a preview on their chatter
card. Reports can be read before they are downloaded, remote images stay
blocked until you ask for them, and Word, Excel and PowerPoint can open in the
Office Online viewer.

![An email file opened in the Odoo file viewer](static/description/screenshot_email.png)

## Features

- **Email and Outlook files**: an `.eml` or `.msg` shows its header, its body
  with embedded pictures and its attachments, read in plain Python.
- **CSV and TSV tables**: an export becomes a table, whatever its delimiter and
  encoding.
- **Previews on the card**: the chatter card shows the subject and sender of a
  mail, or the first rows of a table.
- **Remote images on request**: blocked until one click loads them for that
  message.
- **Office Online**: Word, Excel and PowerPoint in the Microsoft viewer, through
  a signed link that expires after five minutes.
- **Report preview**: the eye next to a report in the Print menu shows it in
  the file viewer; on request, every downloaded report opens in a new tab too.

![Chatter cards with previews](static/description/screenshot_chatter.png)

## Getting started

1. Add the module to your addons path and install it from **Apps**.
2. Click an email, Outlook or CSV attachment anywhere in Odoo, or the eye next
   to a report in the **Print** menu; it opens in the file viewer.
3. For Office files, enable **Settings > General Settings > MS Office Preview**.
   The database must be reachable from the internet.
4. To open downloaded reports in a new tab as well, enable
   **Settings > General Settings > Open Downloaded Reports**.

## Support

Issues and merge requests are welcome. Maintained by
[MuK IT GmbH](https://www.mukit.at), Vienna. Contact: sale@mukit.at
