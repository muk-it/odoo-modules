# MuK AI Browser

[![Odoo 18.0](https://img.shields.io/badge/Odoo-18.0-714B67?style=flat-square)](https://apps.odoo.com/apps/modules/muk_ai_browser)
![Community](https://img.shields.io/badge/CE-%E2%9C%93-1C3A4C?style=flat-square)
![Enterprise](https://img.shields.io/badge/EE-%E2%9C%93-33627E?style=flat-square)
![Odoo.sh](https://img.shields.io/badge/Odoo.sh-%E2%9C%93-1C3A4C?style=flat-square)
![On-Premise](https://img.shields.io/badge/On--Premise-%E2%9C%93-33627E?style=flat-square)
[![License LGPL v3](https://img.shields.io/badge/License-LGPL_v3-blue?style=flat-square)](LICENSE)
[![YouTube demo](https://img.shields.io/badge/YouTube-demo-FF0000?style=flat-square&logo=youtube&logoColor=white)](https://youtu.be/ZcIvjovoFtg)
[![Website mukit.at](https://img.shields.io/badge/Website-mukit.at-243742?style=flat-square)](https://www.mukit.at)

**Your Odoo assistant, in the browser next to it.** The MuK AI chat in
Chrome's side panel reads the pages you work on, clicks, types and fills forms,
and brings what it finds into Odoo. The agent, its rules, its approvals and
its log stay in your Odoo.

![A book shop in the MuK AI tab group, with the chat that created the cheapest book as a product in the side panel](static/description/screenshot.png)

## Features

- **The chat in the side panel**: the same chat, agents and tools as inside
  Odoo, beside any web page.
- **Reads, clicks, types**: reads the page, clicks, types, fills whole forms,
  scrolls and takes screenshots, in a tab group named "MuK AI".
- **Odoo records in the group**: looks up and creates records, and opens the
  record it made in a tab next to the website.
- **A plan first**: a task of several steps starts with a plan you approve,
  naming the sites it needs.
- **Allow, ask or block per site**: rules for one user or for everyone; form
  submits and words like pay or delete always ask first.
- **Never the risky fields**: it never types into password, payment card or
  one-time code fields and never uploads a file.

![The Site Permissions list beside a web order form filled from an Odoo contact](static/description/screenshot_sites.png)

## Getting started

1. Install **MuK AI Browser** from **Apps**; it needs **MuK AI** with a
   provider set up.
2. Install the
   [MuK AI Browser extension](https://chromewebstore.google.com/detail/fecogbhcchendbojonbojofkiehdacne)
   in Chrome 116 or newer, or in Edge, open its options, enter your Odoo
   address and click **Connect**.
3. Log in to Odoo in the tab that opens: it pairs the browser and closes
   itself.
4. Set what the assistant may do on a site without a rule under
   **MuK AI > Settings > Extensions > Browser**, and the site rules under
   **MuK AI > Configuration > Site Permissions**.
5. Open the side panel on any page, and ask.

## Support

Issues and merge requests are welcome. The extension is open source under
Apache-2.0: [muk-ai-browser-extension](https://github.com/muk-it/muk-ai-browser-extension).
Maintained by [MuK IT GmbH](https://www.mukit.at), Vienna. Contact:
sale@mukit.at
