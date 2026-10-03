# MuK Batch Actions

[![Odoo 20.0](https://img.shields.io/badge/Odoo-20.0-714B67?style=flat-square)](https://apps.odoo.com/apps/modules/muk_web_actions)
![Community](https://img.shields.io/badge/CE-%E2%9C%93-1C3A4C?style=flat-square)
![Enterprise](https://img.shields.io/badge/EE-%E2%9C%93-33627E?style=flat-square)
![Odoo.sh](https://img.shields.io/badge/Odoo.sh-%E2%9C%93-1C3A4C?style=flat-square)
![On-Premise](https://img.shields.io/badge/On--Premise-%E2%9C%93-33627E?style=flat-square)
[![License LGPL v3](https://img.shields.io/badge/License-LGPL_v3-blue?style=flat-square)](LICENSE)
[![YouTube demo](https://img.shields.io/badge/YouTube-demo-FF0000?style=flat-square&logo=youtube&logoColor=white)](https://youtu.be/zWmmPZskd5g)
[![Website mukit.at](https://img.shields.io/badge/Website-mukit.at-243742?style=flat-square)](https://www.mukit.at)

**Run big selections in batches, not in one request.** Server actions and
reports from the Actions and Print menus run in slices of a size you choose,
behind a progress bar, and each slice is its own transaction.

![An action running fifty contacts at a time](static/description/screenshot_progress.png)

## Features

- **Below the server timeout**: one request per batch, so thousands of
  selected records never have to fit into a single call.
- **Progress you can watch**: a progress bar counts the batches and estimates
  the time left.
- **One file per record**: a batched report downloads a PDF for every selected
  record instead of one merged document.
- **A failure stops, it does not undo**: each batch commits on its own, and the
  batches before a failing one stay saved.
- **Standard until you flag it**: actions and reports without Execute in Batch
  behave exactly as in standard Odoo.

![Execute in Batch and Batch Size on a server action](static/description/screenshot_action.png)

## Getting started

1. Install the module from **Apps**.
2. In debug mode, turn on _Execute in Batch_ on a server action in **Settings >
   Technical > Server Actions** and set its _Batch Size_, or on a PDF or text
   report in **Settings > Technical > Reports**. It must be in the Actions or
   Print menu of its model.
3. Select records and pick the action or report as usual.

## Support

Issues and merge requests are welcome on the public repository; they are read,
but no response time is promised. Maintained by
[MuK IT GmbH](https://www.mukit.at), Vienna. Contact: sale@mukit.at
