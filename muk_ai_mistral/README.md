# MuK AI Mistral

Adds **Mistral AI** as a first-class provider for `muk_ai`. Pick
*Mistral AI*, paste your API key, and the whole catalogue is already
there — **Mistral Large**, **Mistral Medium 3**, **Mistral Small**, the
**Magistral** reasoning models, **Pixtral** vision, **Codestral**,
**Ministral** and the open **Mistral Nemo**. The chat, agents, tools
and approval flow of MuK AI all work unchanged.

Depends only on `muk_ai` — the Mistral translator is self-contained.

## Installation

To install this module, you need to:

Download the module and add it to your Odoo addons folder. Afterward,
log on to your Odoo server and go to the Apps menu. Trigger the debug
mode and update the list by clicking on the "Update Apps List" link.
Now install the module by clicking on the install button.

## Upgrade

To upgrade this module, you need to:

Download the module and add it to your Odoo addons folder. Restart the
server and log on to your Odoo server. Select the Apps menu and
upgrade the module by clicking on the upgrade button.

## What ships

A new Selection value — **Mistral AI** — and ten pre-seeded
`muk_ai.model` records covering the current Mistral line-up, each with
its context window and pricing for built-in usage and cost tracking.
Models use Mistral's stable `-latest` aliases.

## Capabilities

Talks to Mistral's **Conversations API** (`POST /v1/conversations`,
stateless) with live token streaming, function/tool calling against the
`muk_mcp` registry, image input (Pixtral) and structured output — plus
the full set of Mistral built-in connectors, wired to the same capability
toggles the other muk_ai providers use:

- **Web search** — `web_search` connector, with inline source citations
- **Code interpreter** — `code_interpreter` connector; code and output
  are rendered as fenced blocks
- **Image generation** — `image_generation` connector; generated images
  are downloaded and embedded inline

Custom function tools and built-in connectors can run together in the
same request.

## Configuration

Open *Settings → MuK AI → Providers*, select **Mistral AI**, paste your
[Mistral API key](https://console.mistral.ai/), click **Test
Connection**, pick a default model and start chatting.

## Credits

### Authors

* MuK IT

### Contributors

* Mathias Markl <mathias.markl@mukit.at>

### Maintainer

This module is maintained by [MuK IT GmbH](https://www.mukit.at).
