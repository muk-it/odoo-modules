# MuK Cookie Consent

[![Odoo 20.0](https://img.shields.io/badge/Odoo-20.0-714B67?style=flat-square)](https://apps.odoo.com/apps/modules/muk_website_cookies_consent)
![Community](https://img.shields.io/badge/CE-%E2%9C%93-1C3A4C?style=flat-square)
![Enterprise](https://img.shields.io/badge/EE-%E2%9C%93-33627E?style=flat-square)
![Odoo.sh](https://img.shields.io/badge/Odoo.sh-%E2%9C%93-1C3A4C?style=flat-square)
![On-Premise](https://img.shields.io/badge/On--Premise-%E2%9C%93-33627E?style=flat-square)
[![License LGPL v3](https://img.shields.io/badge/License-LGPL_v3-blue?style=flat-square)](LICENSE)
[![YouTube demo](https://img.shields.io/badge/YouTube-demo-FF0000?style=flat-square&logo=youtube&logoColor=white)](https://youtu.be/TsmTtG9hDXU)
[![Website mukit.at](https://img.shields.io/badge/Website-mukit.at-243742?style=flat-square)](https://www.mukit.at)

**Ask per purpose, block until granted, keep the proof.** A consent manager in
place of Odoo's cookies bar: a choice per purpose, third-party scripts held back
per service, Google Consent Mode v2 and a record of every decision.

![The first layer: two equal answers, the details and the cookie policy](static/description/screenshot_banner.png)

## Features

- **A choice per purpose**: functional, statistics and marketing switched on one
  by one, each listing the cookies it covers.
- **Blocking per service**: scripts and embeds are removed server-side until
  their purpose is granted; one click allows a single embed.
- **Consent Mode and GPC**: all seven Google Consent Mode v2 signals, basic or
  advanced, and Global Privacy Control always honoured.
- **A consent log**: every decision filed append-only with the disclosure the
  visitor was shown, never a readable IP.
- **A registry and a weekly scan**: Odoo's own cookies declared out of the box,
  undeclared ones put up for review.
- **Usable by everyone**: WCAG 2.2 AA, in English, German, French, Spanish and
  Italian.

![The preference centre, one switch per purpose](static/description/screenshot_preferences.png)

## Getting started

1. Install the module from **Apps**.
2. Turn on **Cookies Bar** in the **Cookie Consent** section of
   **Website > Configuration > Settings**, and pick the Consent Mode, the policy
   version and the policy page.
3. Set the layout in the website editor by selecting the Cookies Bar block, and
   add your own third parties under **Website > Configuration > Cookie
   Consent**.

![One Accept all in the consent log](static/description/screenshot_consent.png)

## Support

Issues and merge requests are welcome. A registry filled in for your own third
parties, or a fix on a deadline, is paid work, quoted up front. Maintained by
[MuK IT GmbH](https://www.mukit.at), Vienna. Contact: sale@mukit.at
