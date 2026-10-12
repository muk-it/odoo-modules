# MuK AI Decision

[![Odoo 17.0](https://img.shields.io/badge/Odoo-17.0-714B67?style=flat-square)](https://apps.odoo.com/apps/modules/muk_ai_decision)
![Community](https://img.shields.io/badge/CE-%E2%9C%93-1C3A4C?style=flat-square)
![Enterprise](https://img.shields.io/badge/EE-%E2%9C%93-33627E?style=flat-square)
![Odoo.sh](https://img.shields.io/badge/Odoo.sh-%E2%9C%93-1C3A4C?style=flat-square)
![On-Premise](https://img.shields.io/badge/On--Premise-%E2%9C%93-33627E?style=flat-square)
[![License LGPL v3](https://img.shields.io/badge/License-LGPL_v3-blue?style=flat-square)](LICENSE)
[![YouTube demo](https://img.shields.io/badge/YouTube-demo-FF0000?style=flat-square&logo=youtube&logoColor=white)](https://youtu.be/05VsEYsSOT4)
[![Website mukit.at](https://img.shields.io/badge/Website-mukit.at-243742?style=flat-square)](https://www.mukit.at)

**Answer the questions you ask about every record, in about a second.** A
decision model reads a ticket, a lead or any text and answers fixed questions:
one choice out of a list, a score on a scale, or the chance of a yes, each with
its confidence. Use it to fill fields, route records and start an AI agent only
where one is needed.

![A decision action with four question cards for helpdesk tickets](static/description/screenshot.png)

## Features

- **Questions instead of prompts**: Decide with AI is a server action for any
  model; selection, many2one and tags fields bring their own options.
- **Written only when sure**: below its confidence an answer is never written,
  and the action for unsure decisions takes the record over.
- **Answers that route**: an answer runs another action on the records that
  gave it, or that the model was unsure about.
- **Agents only where needed**: a yes or no decision step in front of an agent
  starts its chats only for the records that need one.
- **The decide tool**: agents check texts, records or a whole domain in one
  call: spam or not, which tags, which team.
- **Hosted, local or what you have**: any System One server, TypeSafe Jev in the
  cloud or Laya behind Decis on your own hardware, or the small model of your
  chat provider; every decision is logged with its cost.

![Helpdesk tickets with their team, tags and a refund check after the triage](static/description/screenshot_tickets.png)

## Getting started

1. Under **MuK AI > Configuration > Providers**, give _TypeSafe_ its API key or
   _Decis_ the address of your server, or set a **Default Decision Model** on a
   chat provider.
2. Under **MuK AI > Automation > Decision Actions**, create an action for a
   model and add its questions.
3. Run it from the **Actions** menu of a list, an automation rule or a schedule,
   and read every answer under **MuK AI > Reports > Decision Logs**.

## Support

Issues and merge requests are welcome. Maintained by
[MuK IT GmbH](https://www.mukit.at), Vienna. Contact: sale@mukit.at
