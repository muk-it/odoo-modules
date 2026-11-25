# MuK MCP Skills

[![Odoo 20.0](https://img.shields.io/badge/Odoo-20.0-714B67?style=flat-square)](https://apps.odoo.com/apps/modules/muk_mcp_skills)
![Community](https://img.shields.io/badge/CE-%E2%9C%93-1C3A4C?style=flat-square)
![Enterprise](https://img.shields.io/badge/EE-%E2%9C%93-33627E?style=flat-square)
![Odoo.sh](https://img.shields.io/badge/Odoo.sh-%E2%9C%93-1C3A4C?style=flat-square)
![On-Premise](https://img.shields.io/badge/On--Premise-%E2%9C%93-33627E?style=flat-square)
[![License LGPL v3](https://img.shields.io/badge/License-LGPL_v3-blue?style=flat-square)](LICENSE)
[![YouTube demo](https://img.shields.io/badge/YouTube-demo-FF0000?style=flat-square&logo=youtube&logoColor=white)](https://youtu.be/MLmipAWmeSQ)
[![Website mukit.at](https://img.shields.io/badge/Website-mukit.at-243742?style=flat-square)](https://www.mukit.at)

**Teach Claude how your team works in Odoo.** Your AI client already reaches
Odoo over MCP. Now write down how things are done: a skill is a procedure with
its files, kept in Odoo and loaded by the client when a request fits.

![The list of MCP skills](static/description/screenshot.png)

## Features

- **Name and description**: the name is what a user can call it by, the
  description is what the client matches a request against.
- **Plain instructions**: markdown, the way you would explain it to a new
  colleague.
- **Files next to it**: a tone guide, a checklist or a template the client
  reads when the instructions send it there.
- **Groups decide who gets it**: a skill limited to a group is not listed, not
  found and not readable for anyone else.
- **Every version is verified**: each file is listed with its size and digest,
  so a client notices a change.

![Claude Code loading a skill from Odoo](static/description/screenshot_claude.png)

## Getting started

1. Install the module next to **MuK MCP Server**.
2. Open **Settings > MCP > Catalog > Skills** and write a skill: name,
   description, instructions, and files if it needs them.
3. Connect a client with **Settings > MCP > Connect**, then ask for what the
   skill describes or call it by its name, in Claude Code
   `/odoo:quote-follow-up`.

Skills need a client with the Skills extension of MCP and the protocol
revision `2026-07-28`.

## Support

Issues and merge requests are welcome. Maintained by
[MuK IT GmbH](https://www.mukit.at), Vienna. Contact: sale@mukit.at
