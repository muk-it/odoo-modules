# MuK MCP Access

[![Odoo 20.0](https://img.shields.io/badge/Odoo-20.0-714B67?style=flat-square)](https://apps.odoo.com/apps/modules/muk_mcp_access)
![Community](https://img.shields.io/badge/CE-%E2%9C%93-1C3A4C?style=flat-square)
![Enterprise](https://img.shields.io/badge/EE-%E2%9C%93-33627E?style=flat-square)
![Odoo.sh](https://img.shields.io/badge/Odoo.sh-%E2%9C%93-1C3A4C?style=flat-square)
![On-Premise](https://img.shields.io/badge/On--Premise-%E2%9C%93-33627E?style=flat-square)
[![License LGPL v3](https://img.shields.io/badge/License-LGPL_v3-blue?style=flat-square)](LICENSE)
[![YouTube demo](https://img.shields.io/badge/YouTube-demo-FF0000?style=flat-square&logo=youtube&logoColor=white)](https://youtu.be/_0uXgZ270eA)
[![Website mukit.at](https://img.shields.io/badge/Website-mukit.at-243742?style=flat-square)](https://www.mukit.at)

**Decide which models an AI agent can reach.** An allowlist for the MuK MCP
Server: the models an agent may read, the ones it may also change, and the
records it sees in each. Whatever is not on the list stays out of reach,
whoever the key belongs to.

![The MCP model access list](static/description/screenshot.png)

## Features

- **Only what you list**: once the list holds a model, every other one is
  refused, and the model listing no longer names it.
- **Read or write, per model**: create, update, delete and method calls need
  the write switch.
- **A record domain per model**: like a record rule for agents, built in
  Odoo's domain editor, with `user`, `company_id` and `company_ids` available.
- **Every way in**: reads, writes, exports, reports, method calls and the files
  behind a record go through the same check.
- **Off without uninstalling**: archive the entries and the server is open
  again.

![A call to a model that is not listed, refused in the MCP Playground](static/description/screenshot_playground.png)

## Getting started

1. Install the module next to **MuK MCP Server**. Nothing changes until the
   first model is listed.
2. Open **Settings > MCP > Authentication > Access** and use **Add Models**.
3. Switch on **Write** where the agent should change data, and add a
   **Record Domain** where it should see only part of a model.

## Support

Issues and merge requests are welcome. Maintained by
[MuK IT GmbH](https://www.mukit.at), Vienna. Contact: sale@mukit.at
