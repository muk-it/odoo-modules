# MuK Calendar

[![Odoo 20.0](https://img.shields.io/badge/Odoo-20.0-714B67?style=flat-square)](https://apps.odoo.com/apps/modules/muk_calendar)
![Community](https://img.shields.io/badge/CE-%E2%9C%93-1C3A4C?style=flat-square)
![Enterprise](https://img.shields.io/badge/EE-%E2%9C%93-33627E?style=flat-square)
![Odoo.sh](https://img.shields.io/badge/Odoo.sh-%E2%9C%93-1C3A4C?style=flat-square)
![On-Premise](https://img.shields.io/badge/On--Premise-%E2%9C%93-33627E?style=flat-square)
[![License LGPL v3](https://img.shields.io/badge/License-LGPL_v3-blue?style=flat-square)](LICENSE)
[![YouTube demo](https://img.shields.io/badge/YouTube-demo-FF0000?style=flat-square&logo=youtube&logoColor=white)](https://youtu.be/p0gxzsE_dgg)
[![Website mukit.at](https://img.shields.io/badge/Website-mukit.at-243742?style=flat-square)](https://www.mukit.at)

**Any record in your calendar, every calendar in your phone.** A calendar shows
the records of any model on one of their dates, such as task deadlines or
scheduled deliveries, and follows every change. Any calendar can be shared as a
secret iCal link for Google, Apple or Outlook.

![Task deadlines in the calendar beside the meetings](static/description/screenshot_calendar.png)

## Features

- **Records as events**: pick a model, the date to place its records on, an
  optional end date and a filter.
- **Always current**: creating, moving or deleting a record updates its event
  at once, and a nightly run catches everything else.
- **Attendees from the record**: a contact or user field becomes the event's
  attendees.
- **Read as the owner**: the owner's rights pick the records, and every viewer
  only sees the events of records they may open.
- **iCal subscription**: one link per calendar, with all details or busy times
  only, renewable and revocable.

![A record calendar showing open tasks on their deadline](static/description/screenshot_setup.png)

## Getting started

1. Add the module to your addons path and install it from **Apps**.
2. In **Calendar**, create a calendar from the side panel as an administrator
   and choose the model, the date and the filter. Share it with the users who
   should see it.
3. To subscribe from another app, open a calendar's menu in the side panel of
   **Calendar**, click **Create iCal link** and copy the link.

## Support

Issues and merge requests are welcome. Maintained by
[MuK IT GmbH](https://www.mukit.at), Vienna. Contact: sale@mukit.at
