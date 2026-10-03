# MuK List Mode

[![Odoo 20.0](https://img.shields.io/badge/Odoo-20.0-714B67?style=flat-square)](https://apps.odoo.com/apps/modules/muk_web_list_mode)
![Community](https://img.shields.io/badge/CE-%E2%9C%93-1C3A4C?style=flat-square)
![Enterprise](https://img.shields.io/badge/EE-%E2%9C%93-33627E?style=flat-square)
![Odoo.sh](https://img.shields.io/badge/Odoo.sh-%E2%9C%93-1C3A4C?style=flat-square)
![On-Premise](https://img.shields.io/badge/On--Premise-%E2%9C%93-33627E?style=flat-square)
[![License LGPL v3](https://img.shields.io/badge/License-LGPL_v3-blue?style=flat-square)](LICENSE)
[![YouTube demo](https://img.shields.io/badge/YouTube-demo-FF0000?style=flat-square&logo=youtube&logoColor=white)](https://youtu.be/m9aa7KmODGI)
[![Website mukit.at](https://img.shields.io/badge/Website-mukit.at-243742?style=flat-square)](https://www.mukit.at)

**Open the form or edit in the row, list by list.** A switch beside the pager
decides what a click on a row does: open the record in its form, as Odoo always
has, or edit it right there in the list, several rows at once if you select
them. The lines inside a form get the same choice.

![The mode switch between the pager and the view switcher](static/description/screenshot_read.png)

## Features

- **Open Form View**: a click on a row opens the record in its form, with the
  breadcrumb back to the list.
- **Inline Edit Mode**: click a cell, type, move on with Tab; tick several rows
  and one value is written to all of them.
- **Inside forms too**: order lines and every other list in a form carry a
  toggle of their own in the header.
- **Remembered per list**: the mode is kept per user, action and model, and per
  field for the lists in a form.
- **Only where editing is allowed**: without the right to edit, or on a
  read-only list, the switch does not appear.

![Four contacts selected and edited inline at once](static/description/screenshot_edit.png)

## Getting started

1. Install the module from **Apps**. There is nothing to configure.
2. Open any list you are allowed to edit and pick **Open Form View** or
   **Inline Edit Mode** beside the pager.
3. In a form, use the toggle in the last column header of a line list.

## Support

Issues and merge requests are welcome. Another mode, a default per list or a fix
on a deadline is paid work, quoted up front. Maintained by
[MuK IT GmbH](https://www.mukit.at), Vienna. Contact: sale@mukit.at
