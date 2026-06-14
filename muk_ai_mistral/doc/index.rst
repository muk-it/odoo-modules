===============
MuK AI Mistral
===============

Adds **Mistral AI** as a first-class provider for ``muk_ai``. The full
Mistral catalogue ships pre-seeded with context windows and pricing, so
the only thing left to configure is your API key.

Models
======

Seeded ``muk_ai.model`` records (Mistral ``-latest`` aliases):

- ``mistral-large-latest`` — Mistral Large
- ``mistral-medium-latest`` — Mistral Medium 3 (default)
- ``mistral-small-latest`` — Mistral Small 3
- ``magistral-medium-latest`` — Magistral Medium (reasoning)
- ``magistral-small-latest`` — Magistral Small (reasoning)
- ``pixtral-large-latest`` — Pixtral Large (vision)
- ``codestral-latest`` — Codestral (code, 256K context)
- ``ministral-8b-latest`` — Ministral 8B
- ``ministral-3b-latest`` — Ministral 3B
- ``open-mistral-nemo`` — Mistral Nemo (open weight)

Capabilities
============

The provider speaks Mistral's stateless **Conversations API**
(``POST https://api.mistral.ai/v1/conversations``) with:

- Live token and tool-call streaming
- Function / tool calling via the ``muk_mcp`` tool registry
- Image input (Pixtral) and inline document attachments
- Structured output (JSON schema response format)
- **Web search** connector (``web_search``) with inline source citations
- **Code interpreter** connector (``code_interpreter``); code and output
  rendered as fenced blocks
- **Image generation** connector (``image_generation``); generated
  images downloaded via the files endpoint and embedded inline

The built-in connectors are gated by the same ``supports_web_search`` /
``supports_image_generation`` / ``supports_code_interpreter`` capability
flags the other muk_ai providers expose, and can be combined with custom
function tools in a single request.

Configuration
=============

#. Install the module (depends only on ``muk_ai``).
#. Open *Settings → MuK AI → Providers* and select **Mistral AI**.
#. Paste your Mistral API key and click **Test Connection**.
#. Pick a default model and start chatting.

Extending
=========

The provider class registers itself by mutating the shared registry at
import time::

    from odoo.addons.muk_ai.providers import REGISTRY

    from .mistral import MistralProvider

    REGISTRY[MistralProvider.name] = MistralProvider

Add further ``muk_ai.model`` records pointing at ``provider_mistral`` to
expose more models.
