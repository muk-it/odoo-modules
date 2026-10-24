# MuK AI Schedule

[![Odoo 19.0](https://img.shields.io/badge/Odoo-19.0-714B67?style=flat-square)](https://apps.odoo.com/apps/modules/muk_ai_schedule)
![Community](https://img.shields.io/badge/CE-%E2%9C%93-1C3A4C?style=flat-square)
![Enterprise](https://img.shields.io/badge/EE-%E2%9C%93-33627E?style=flat-square)
![Odoo.sh](https://img.shields.io/badge/Odoo.sh-%E2%9C%93-1C3A4C?style=flat-square)
![On-Premise](https://img.shields.io/badge/On--Premise-%E2%9C%93-33627E?style=flat-square)
[![License LGPL v3](https://img.shields.io/badge/License-LGPL_v3-blue?style=flat-square)](LICENSE)
[![YouTube demo](https://img.shields.io/badge/YouTube-demo-FF0000?style=flat-square&logo=youtube&logoColor=white)](https://youtu.be/OhbTXayFli4)
[![Website mukit.at](https://img.shields.io/badge/Website-mukit.at-243742?style=flat-square)](https://www.mukit.at)

**Let an agent wait, then carry on by itself.** An agent pauses its chat until
a time, until a record reaches a state or until somebody replies on a record,
and picks the task up again with the note it left itself, without anybody
watching.

![A chat waiting for a reply on a contact, with Wake now and Stop](static/description/screenshot.png)

## Features

- **Wait for a time**: "check again in an hour" or "send the reminder Monday at
  nine", up to thirty days ahead.
- **Wait for a record**: wake when an invoice is paid, a delivery is done or a
  lead is won. The condition is checked every minute without calling the model.
- **Wait for a reply**: wake when a message or an email is posted on the
  record, and read it in the result.
- **Always a way out**: every wait has a timeout, so a reply that never comes
  still wakes the agent to follow up.
- **You stay in control**: the chat shows what it waits for, with buttons to
  wake or stop it, and typing a message wakes it too.
- **Keep watch**: ask the agent to check every few minutes and report each
  time. It waits again after every check and stops when the outcome is there.
- **Bounded**: each chat may wait as often as the settings allow, and every
  wake-up runs within the usual turn limits.

## Getting started

1. Install **MuK AI Schedule** next to MuK AI.
2. Optionally set **Max waits per chat** in **MuK AI > Settings > Extensions**.
3. Ask an agent to follow something up, for example "remind Acme about the
   invoice and wait for their reply". It calls the wait tool and the chat shows
   what it waits for.

## Support

Issues and merge requests are welcome on the public repository. Paid work, such
as agents that follow up your own processes, goes to
[sale@mukit.at](mailto:sale@mukit.at). MuK IT GmbH, Vienna.
