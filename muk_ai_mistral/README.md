# MuK AI Mistral

[![Odoo 20.0](https://img.shields.io/badge/Odoo-20.0-714B67?style=flat-square)](https://apps.odoo.com/apps/modules/muk_ai_mistral)
![Community](https://img.shields.io/badge/CE-%E2%9C%93-1C3A4C?style=flat-square)
![Enterprise](https://img.shields.io/badge/EE-%E2%9C%93-33627E?style=flat-square)
![Odoo.sh](https://img.shields.io/badge/Odoo.sh-%E2%9C%93-1C3A4C?style=flat-square)
![On-Premise](https://img.shields.io/badge/On--Premise-%E2%9C%93-33627E?style=flat-square)
[![License LGPL v3](https://img.shields.io/badge/License-LGPL_v3-blue?style=flat-square)](LICENSE)
[![YouTube demo](https://img.shields.io/badge/YouTube-demo-FF0000?style=flat-square&logo=youtube&logoColor=white)](https://youtu.be/L112-Y_AF4Q)
[![Website mukit.at](https://img.shields.io/badge/Website-mukit.at-243742?style=flat-square)](https://www.mukit.at)

**Run your Odoo agents on Mistral.** Add Mistral AI to the MuK AI chat with
your own API key. Its models arrive priced and ready, with tools, web search,
code interpreter and image generation, on Mistral's own API.

![An AI chat answered by a Mistral model, with its sources cited inline](static/description/screenshot_chat.png)

## Features

- **Tools and approvals**: the agent calls the same Odoo tools and stops for
  the same approvals; a tool named like one of Mistral's own is renamed on the
  way and back.
- **Web search with sources**: Mistral's own search, with each source cited
  inline where the answer uses it.
- **Code interpreter**: the model runs Python, and the answer shows the code
  and its output.
- **Images, PDFs and JSON**: photos and PDF documents as attachments, and
  structured JSON output where a step needs data.
- **Image generation**: Mistral Medium 3.5 Images is an image model any agent
  can pick, priced per image.
- **Reasoning kept apart**: the model's thinking streams beside the answer; an
  answer cut off at the Max Tokens limit says so.
- **Priced catalogue**: Mistral Large, Medium and Small, Ministral, Codestral
  and Z.ai GLM come with context windows and prices.

![The Mistral AI provider form with the API key and the catalogue of models](static/description/screenshot_provider.png)

## Getting started

1. Install **MuK AI Mistral** from **Apps**; it needs **MuK AI Assistant**.
2. Open **MuK AI > Configuration > Providers > Mistral AI**, paste your Mistral
   API key and click **Test Connection**.
3. Make Mistral the **Default Provider** under **Settings > MuK AI**, or pick
   it on an agent under **MuK AI > Agents**, and switch on **Web Search**, **Code
   Interpreter** or **Image Generation** there.

## Support

Issues and merge requests are welcome. Maintained by
[MuK IT GmbH](https://www.mukit.at), Vienna. Contact: sale@mukit.at
