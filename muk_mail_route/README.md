# MuK Mail Routing

[![Odoo 20.0](https://img.shields.io/badge/Odoo-20.0-714B67?style=flat-square)](https://apps.odoo.com/apps/modules/muk_mail_route)
![Community](https://img.shields.io/badge/CE-%E2%9C%93-1C3A4C?style=flat-square)
![Enterprise](https://img.shields.io/badge/EE-%E2%9C%93-33627E?style=flat-square)
![Odoo.sh](https://img.shields.io/badge/Odoo.sh-%E2%9C%93-1C3A4C?style=flat-square)
![On-Premise](https://img.shields.io/badge/On--Premise-%E2%9C%93-33627E?style=flat-square)
[![License LGPL v3](https://img.shields.io/badge/License-LGPL_v3-blue?style=flat-square)](LICENSE)
[![YouTube demo](https://img.shields.io/badge/YouTube-demo-FF0000?style=flat-square&logo=youtube&logoColor=white)](https://youtu.be/dqVdA5xrNFE)
[![Website mukit.at](https://img.shields.io/badge/Website-mukit.at-243742?style=flat-square)](https://www.mukit.at)

**No email gets lost on the way in.** Emails that match no alias and no
conversation are kept as Lost Emails instead of bouncing. Route each one to a
new or an existing record, in one click with a router.

![Lost Emails with a button per router and the selected email in the preview](static/description/screenshot_lost.png)

## Features

- **Lost Emails**: incoming mail without a home, with sender, content and
  attachments, read in a preview beside the list.
- **A new record per email**: a router creates a lead, a ticket or any record
  from each email, and moves the email onto it.
- **Attach to an existing one**: a router asks which record the email belongs
  to, and can notify its followers.
- **Route without a router**: pick any kind of record, then the record itself,
  and the selected emails move there.
- **Failed Emails**: outgoing mail that could not be delivered, with the reason
  and a button to send it again.

![A router that creates a lead from each email](static/description/screenshot_router.png)

## Getting started

1. Install the module from **Apps**.
2. Open **Discuss > Lost Emails** and route an email with **Route**.
3. For one-click routing, create a router under **Discuss > Configuration >
   Routers**: the target model, and whether an email creates a new record or
   is attached to an existing one.

## Support

Issues and merge requests are welcome on the public repository; no response
time is promised. A router built for your process, or a fix on a deadline, is
paid work. Maintained by [MuK IT GmbH](https://www.mukit.at), Vienna. Contact:
sale@mukit.at
