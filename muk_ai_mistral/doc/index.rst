==============
MuK AI Mistral
==============

Adds Mistral AI as a provider for the MuK AI assistant. The Mistral catalogue
ships pre-seeded with context windows and prices, so the only thing left to
configure is the API key. The provider talks to Mistral's stateless
Conversations API with streaming, tool calling, vision, PDF documents and
structured output, plus Mistral's own web search and code interpreter, and
offers image generation as a catalogued image model.

Installation
============

To install this module, you need to:

Download the module and add it to your Odoo addons folder. Afterward, log on to
your Odoo server and go to the Apps menu. Trigger the debug mode and update the
list by clicking on the "Update Apps List" link. Now install the module by
clicking on the install button.

Upgrade
=======

To upgrade this module, you need to:

Download the module and add it to your Odoo addons folder. Restart the server
and log on to your Odoo server. Select the Apps menu and upgrade the module by
clicking on the upgrade button.

Configuration
=============

Open *MuK AI > Configuration > Providers > Mistral AI*:

- **API Key**: the key from your Mistral account. **Test Connection** checks
  it.
- **Default Chat Model** and **Default Image Model**: set to *Mistral Medium
  3.5* and *Mistral Medium 3.5 Images* on install.
- **Models**: the catalogue, each model with its context window and its rates
  in USD per million tokens, which you can edit:

  ======================== ========================== ========= ===== ======
  Model                    Technical name             Context   Input Output
  ======================== ========================== ========= ===== ======
  Mistral Large 3          ``mistral-large-latest``   262,144   0.50  1.50
  Mistral Medium 3.5       ``mistral-medium-latest``  262,144   1.50  7.50
  Mistral Small 4          ``mistral-small-latest``   262,144   0.15  0.60
  Ministral 3 14B          ``ministral-14b-latest``   262,144   0.20  0.20
  Ministral 3 8B           ``ministral-8b-latest``    262,144   0.15  0.15
  Ministral 3 3B           ``ministral-3b-latest``    131,072   0.10  0.10
  Codestral                ``codestral-latest``       256,000   0.30  0.90
  Z.ai GLM 5.2             ``zai-glm-5-2``            1,048,576 1.40  4.40
  ======================== ========================== ========= ===== ======

  Z.ai GLM 5.2 is a third-party open model hosted by Mistral, in public
  preview, available on some account tiers only, and reads text only; its
  cached input is billed at 0.14. *Mistral Medium 3.5 Images* is the image
  model, at USD 0.10 per image.

To use Mistral everywhere, set it as the **Default Provider** under *Settings
> MuK AI*. To use it for one agent, pick it as the agent's **Provider** under
*MuK AI > Agents*.

Usage
=====

An agent on Mistral works in the AI chat like on any other provider: answers
stream in, tools are called and approvals are asked for as usual. A tool whose
name Mistral reserves, such as ``web_search`` or ``generate_image``, is sent
under a ``muk_ai_`` prefix and mapped back, without any change to the tool.

- **Attachments**: images and PDF documents attached to a message are read by
  the model.
- **Web Search**: set to *Provider Built-in* or *Automatic* on the agent, the
  answer cites its sources inline.
- **Enable Code Interpreter**: the model runs Python, and the answer shows the
  code and its output.
- **Enable Image Generation**: the agent creates pictures with its **Image
  Model**, by default *Mistral Medium 3.5 Images*, through Mistral's image
  generation connector.

The model's reasoning streams separately from the answer, and an answer cut
off at the provider's **Max Tokens** is marked as such.

Credits
=======

Contributors
------------

* Mathias Markl <mathias.markl@mukit.at>

Author & Maintainer
-------------------

This module is maintained by the `MuK IT GmbH <https://www.mukit.at/>`_.

MuK IT is an Austrian company specialized in customizing and extending Odoo.
We develop custom solutions for your individual needs to help you focus on
your strength and expertise to grow your business.

If you want to get in touch please contact us via mail
(sale@mukit.at) or visit our website (https://mukit.at).
