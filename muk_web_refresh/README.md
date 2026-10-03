# MuK Refresh

[![Odoo 20.0](https://img.shields.io/badge/Odoo-20.0-714B67?style=flat-square)](https://apps.odoo.com/apps/modules/muk_web_refresh)
![Community](https://img.shields.io/badge/CE-%E2%9C%93-1C3A4C?style=flat-square)
![Enterprise](https://img.shields.io/badge/EE-%E2%9C%93-33627E?style=flat-square)
![Odoo.sh](https://img.shields.io/badge/Odoo.sh-%E2%9C%93-1C3A4C?style=flat-square)
![On-Premise](https://img.shields.io/badge/On--Premise-%E2%9C%93-33627E?style=flat-square)
[![License LGPL v3](https://img.shields.io/badge/License-LGPL_v3-blue?style=flat-square)](LICENSE)
[![YouTube demo](https://img.shields.io/badge/YouTube-demo-FF0000?style=flat-square&logo=youtube&logoColor=white)](https://youtu.be/dGeMQaWkBbs)
[![Website mukit.at](https://img.shields.io/badge/Website-mukit.at-243742?style=flat-square)](https://www.mukit.at)

**Reload the view you are on, without leaving it.** A refresh button beside the
pager. Double-click it and the view keeps itself current, and an automation rule
can push a reload to everyone who has that model open.

![Auto refresh on, with the countdown beside the pager](static/description/screenshot_auto.png)

## Features

- **Click to reload**: the reload goes through the pager, so filters, grouping
  and your place in the list survive it.
- **Double-click for auto**: lists and kanban views reload on a timer, with a
  countdown next to the button; the choice is kept per view.
- **Quiet in the background**: a hidden tab stops polling until you come back.
- **Reload Views action**: a server action type for automation rules that
  refreshes the open views of a model for every user at once.

![Reload Views as an automation rule action](static/description/screenshot_action.png)

## Getting started

1. Install the module from **Apps**.
2. Click the refresh button left of the pager to reload once; double-click it
   on a list or kanban view to turn auto refresh on or off.
3. To refresh from the backend, add a **Reload Views** action to an automation
   rule under **Settings > Technical > Automation Rules**. Leave **View Types**
   empty for every view, or name them, e.g. `list, kanban`.

The auto refresh interval is the system parameter
`muk_web_refresh.pager_autoload_interval`, in milliseconds (default `30000`).

## Support

Issues and merge requests are welcome. A different interval, another trigger or
a fix on a deadline is paid work, quoted up front. Maintained by
[MuK IT GmbH](https://www.mukit.at), Vienna. Contact: sale@mukit.at
