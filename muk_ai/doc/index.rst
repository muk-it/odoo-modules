================
MuK AI Assistant
================

A complete agentic AI assistant inside Odoo. It ships a chat client with a
full page, a floating window and a systray entry, a session-based agent
runtime, and three LLM providers (OpenAI Responses, Anthropic Messages, Google
Gemini) with live token and reasoning streaming. The assistant talks to your
data through the same ``muk_mcp`` tool registry your external AI clients use:
one source of truth, one permission model, one audit trail.

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

Everything lives under *MuK AI* in the app menu: *Chat*, *Agents*, and for
administrators *Reports* (sessions, tool logs, the approval log), *MCP* (the
custom tools and the playground of ``muk_mcp``), *Configuration* (providers,
models, spaces) and *Settings*.

**Providers**

*MuK AI > Configuration > Providers* holds one record per provider
implementation: OpenAI, Anthropic and Google. A provider needs an **API Key**;
the other fields have working defaults:

- **Default Chat Model** and **Default Image Model**: the models an agent gets
  when it names none.
- **Region**: the endpoint the requests go to, where the vendor offers more
  than one.
- **Max Tokens**: the completion-token cap per request.
- **Request Timeout**, **Idle Timeout** and **Image Timeout**: seconds before
  a request, a silent stream or an image request is given up.
- **Rate Limit**: chats a single user may start per minute, ``0`` for no cap.

**Test Connection** sends a short probe and reports success or the provider's
error without leaving the form.

**Models**

The model catalogue under *MuK AI > Configuration > Models*, also shown on
each provider, ships prefilled with the vendors' current models. Each carries
its technical name, its modality (chat or image), its context window, its
input, output, cache-read and cache-write rates, and the reasoning-effort tiers
it accepts. The rates drive the cost shown in the chat and the usage reports,
with prompt-cached input billed at its cache rate. Models the vendors retire
are removed, so every entry still answers.

**Settings**

*MuK AI > Settings* opens the assistant's block in the general settings:

- **Default Provider** and **Default Agent**: used when an agent names no
  provider, and for a new chat that names no agent.
- **Search Backend**: the search API behind the ``web_search`` tool; empty
  keeps the provider's built-in search where it has one.
- **Iteration Limit**: tool-calling rounds per worker slice; the model is
  warned shortly before the limit so it can wrap up.
- **Turn Runtime** and **Slice Runtime**: wall-clock budgets for a whole user
  turn and for one worker slice. A slice that runs out is checkpointed and
  resumed by a fresh worker; a turn that runs out stops with an error.
- **Cost Limit**: the maximum spend of one user turn in the model's price
  currency, ``0`` for no limit.
- **Housekeeping**: whether and after how many days old chats are deleted.

**Agents**

An agent is a named preset under *MuK AI > Agents*. A *General Assistant* is
installed with the module.

- **System Prompt**: the instructions, rendered with placeholders such as
  ``{{ user.name }}``, ``{{ company.name }}`` and ``{{ today }}``. Every edit
  is kept, and the **Prompt History** button restores an earlier version.
- **Provider** and **Chat Model**: pin the agent to a vendor, a model, or
  both. Empty follows the defaults, and the field shows which model that is.
  The **Image**, **TTS** and **STT** models follow the same rule.
- **Reasoning**: how hard the model thinks before it answers. Only the tiers
  the model supports are offered, the field is hidden for models without
  one, and a provider that refuses a tier is asked again without it.
- **Web Search**, **Images** and **Code Interpreter**: the built-in
  capabilities. Web search is *Off*, *Automatic*, *Provider Built-in* or
  *Search Backend*; a capability nothing can serve is named in an alert on
  the form, with the setting that repairs it.
- **Read-only Mode**: the agent can only call read tools. This is enforced by
  the server, not asked of the model.
- **Tool Filter**: the tools the agent may call; empty allows every tool.
- **Essential Tools**: the tools whose full description is sent with every
  request. Every other tool is announced by name and loaded by the model when
  it needs it, which keeps requests small.
- **Approval Mode**: *Ask on writes* or *Never ask*, see *Approvals* below.
- **Allow Handoff**: other agents may hand a chat to this one.
- **Suggestions**: starter prompts shown in an empty chat.

**Sensitive models**

An agent asks before it writes to a model marked **Sensitive for AI**, a
switch on the model under *Settings > Technical > Database Structure >
Models*. Users are marked out of the box; mark every model whose records an
agent must not change unseen.

**Access groups**

Internal users open the chat, manage their own chats and read the agents.
Administrators manage every chat, the agents and the providers, and read the
approval log and the tool logs. A chat is private to the person who started it
and to the colleagues it is shared with.

Usage
=====

**Chatting**

Open *MuK AI > Chat*, or the robot icon in the top bar, which lists the recent
chats and opens a new one in a window (``Alt+Shift+B``) or the full page
(``Alt+Shift+F``). Type a question and press ``Enter``; ``Shift+Enter`` adds a
line. The answer streams in as it is written. Tool calls show as cards above
it, several in a row collapse into one *Used N tools* card, and each fills in
its arguments and its result as they arrive. The send button stops a running
answer. The full page keeps the open chat in its address, so a link to
``/odoo/ai-chat?session_id=<id>`` opens that chat.

**The chat window**

The window and the full page show the same chat. A window on a form or a list
knows what you are looking at and shows it as a pin, so "this order" or "the
current list" need no explaining; a record the agent opens becomes the new
context, and ``/unpin`` clears it. Expanding a window moves the chat to the
full page with the unsent draft and its attachments.

**Reshaping a view**

On a list, kanban, pivot or graph, ask for a change to the view itself:
"group these by salesperson", "only drafts", "as a bar chart". The agent
drives the search of the view in your browser tab, applies filters, group-bys,
field searches and measures, switches the view type, and reports what it
changed. The facets stay in the search bar like any you set yourself.

**Approvals**

When an agent wants to create, change, delete or call a method on a record of
a sensitive model, the chat stops on a card that shows the record and every
field before and after. **Approve** runs the call once; **Allow for session**
runs it and lets the same kind of call through for the rest of this chat;
**Reject** tells the agent the call was refused, so it can look for another
way. Every decision is recorded under *MuK AI > Reports > Approval Log*. A new
chat starts with nothing allowed. Agents set to *Never ask* skip the card.

**Questions from the agent**

An agent that needs a decision asks with a card of its own, often with the
answers to pick from. The chat waits, and the answer continues the turn where
it stopped.

**Sources and artifacts**

The records and web pages an answer was built from are listed under it, each
one click from the record or the page. The paperclip in the header opens the
artifacts panel with every file attached to or generated in the chat, and the
sources, side by side.

**Attachments**

Drop a file onto the composer, paste a screenshot, or use the clip. Images,
PDFs, plain text, CSV and Markdown are sent to the provider in the form it
reads natively; text files are inlined.

**Spaces**

The sidebar groups chats into spaces. Create one with the ``+`` next to
*Spaces*, drag chats into it and out again, and drag a space by its grip to
reorder the list. A space has a name, an icon and an optional default agent
for every chat started in it. Unread chats are counted per space. Modules can
add system spaces whose chats are collected by a rule, such as *Shared with
Me*. Administrators manage all spaces under *MuK AI > Configuration > Spaces*.

**Sharing and handover**

The line above the composer names who can read the chat; **Share** adds or
removes colleagues. They see the whole transcript, every tool call and every
answer, live as it is written, and cannot reply, rename it or share it on.
The forward icon in the header, or ``/handover``, hands the chat to a
colleague, who gets it marked unread with a notification; you stay on as a
reader.

**Conversation controls**

Hover a message to copy it, **rewind** the chat to before it, or **branch**
the history up to it into a new chat; the last answer can be regenerated. The
search icon in the header finds words in the conversation. Slash commands in
the composer: ``/help``, ``/clear`` (start over in this chat), ``/compact``
(summarise older turns to free context), ``/unpin``, ``/agent`` and
``/handover``.

**Agents and handoff**

The agent of a chat is chosen in the header. An agent can hand the chat to
another agent that fits among those that allow handoff; the switch is marked
in the transcript.

**Context and cost**

The ring under the chat bar shows how full the model's context window is.
Click it for the input and output tokens, the rounds and the cost of the last
turn and of the whole chat. A chat that nears the end of its context window
is summarised and continues.

**Notifications**

The robot icon shows a dot while a chat is running and counts the chats
waiting for you. Users with inbox notifications also get a notice when a chat
finishes.

**Long turns**

A long turn runs in slices: when a slice reaches its time budget the chat is
saved and a worker picks it up again, until the turn ends or reaches its own
limits. On a threaded server a turn starts as soon as the request that queued
it has answered; on a server with workers it runs in the AI session worker
cron. Set the system parameter ``muk_ai.dispatch_mode`` to ``cron`` to always
use the cron.

**Odoo's own AI apps**

On Enterprise, Odoo's AI apps and this assistant run on the same database
side by side: each keeps its own icon, its own chats and its own settings.

**Extending**

A provider is a class in your own addon, registered in
``odoo.addons.muk_ai.providers.REGISTRY``:

.. code-block:: python

    from odoo.addons.muk_ai.providers import REGISTRY
    from odoo.addons.muk_ai.providers.base import ProviderBase


    class MistralProvider(ProviderBase):
        name = 'mistral'
        label = 'Mistral'
        default_model = 'mistral-large-latest'
        default_url = 'https://api.mistral.ai/v1'

        def headers(self):
            return {'Authorization': f'Bearer {self.api_key}'}

        def request(
            self,
            inputs,
            tools_schema=None,
            text_schema=None,
            on_delta=None,
            model=None,
            enable_web_search=False,
            enable_code_interpreter=False,
            cache_key=None,
            reasoning_effort=None,
        ):
            ...


    REGISTRY[MistralProvider.name] = MistralProvider

Add a ``muk_ai.provider`` record and its ``muk_ai.model`` records in the
addon's data; the settings, the agents and the catalogue pick them up.

Tools come from ``muk_mcp``: a tool an addon registers there is available to
the agents with the same access rights, and ``registry='odoo'`` on the
decorator keeps it from external MCP clients. A tool that runs in the user's
browser tab, the way view reshaping does, is registered in the
``muk_ai.client_tools`` registry.

**Security and audit**

Agents act with the access rights of the user in the chat. Every chat keeps
its full event log, tool calls and results included, and ``muk_mcp`` logs
every tool call; streaming runs on a channel per chat that only its readers
are given.

Credits
=======

Contributors
------------

* Mathias Markl <mathias.markl@mukit.at>
* Kerrim Abd E-Hamed <kerrim.adbelhamed@mukit.at>

Author & Maintainer
-------------------

This module is maintained by the `MuK IT GmbH <https://www.mukit.at/>`_.

MuK IT is an Austrian company specialized in customizing and extending Odoo.
We develop custom solutions for your individual needs to help you focus on
your strength and expertise to grow your business.

If you want to get in touch please contact us via mail
(sale@mukit.at) or visit our website (https://mukit.at).
