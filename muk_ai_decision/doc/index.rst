===============
MuK AI Decision
===============

Adds decision models to the MuK AI assistant. A decision model reads a text or
a record and answers typed questions: one choice out of a list, a score on a
scale, or the probability of a yes, each with its confidence. One service
answers them for every module, through any server speaking the System One API,
TypeSafe Jev in the cloud or a self-hosted Laya, or a small chat model of an
existing provider. Every decision is logged with its model, answers, duration
and cost. A Decide with AI server action fills fields, routes records to other
actions and flags unsure ones from any automation rule or scheduled action, a
decision step in front of an agent starts its chats only where they are
needed, and agents decide about texts or records through the decide tool.

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

Open *MuK AI > Configuration > Providers*. Every provider has a **Default
Decision Model**; the decision providers are asked first, then the chat
providers, each in list order, and the next one takes over when one fails:

- **System One Compatible**: any server speaking the System One decision API.
  Two accounts ship ready to fill in: *typesafe* decides with *Jev* in the
  TypeSafe cloud once its API key is set, *decis* with *Laya* on a self-hosted
  Decis server once its **Custom URL** is set, with a key only when the server
  asks for one. An account without either is skipped; **Test Connection**
  answers one question.
- **OpenAI**, **Anthropic** and **Google**: their smallest chat model answers
  decisions through structured output when no System One account is active.
  The model reports its own confidence, which is less reliable than the
  probabilities of a decision model. **Parallel Decisions** sets how many records are sent at
  once; set it to 1 for a self-hosted server on a CPU.

Decisions are deleted after the **Log Retention** of the MCP audit logs under
*Settings > MuK AI*.

Usage
=====

**Decide with AI** (*MuK AI > Automation > Decision Actions*) is a server action
for any model, run from an automation rule, a scheduled action or the Action
menu of a list:

- **Questions**: **What should the AI do?** sets the goal. **Fill a Field**
  fills a yes/no, selection, many2one or tags field, limited to its
  **Candidates**; a tags field asks one yes/no per tag and its **Operation**
  either adds the tags that apply, or adds them and also removes the tags that
  confidently do not apply. **Own Categories** and **Score** list their own options or levels,
  and **Yes/No Check** asks a question to route on. An answer is written only
  above its **Min. Confidence**.
- **Options**: a table of the categories, or the levels of a score from
  lowest to highest, each with a description as a hint and a **Run Action**
  for the records answered with it, for example an AI agent action for
  complaints. A **Yes/No Check** runs its action on the answer yes or no.
- **When Unsure**: per question, an action run on the records whose answer
  stays below its confidence, for example one that schedules an activity to
  check them.
- **Reads**: the fields the decision model reads, of any type, each with its
  label and readable value and long texts cut short, preset to the name and
  the list columns, with **Read Last Messages** that many of the last emails
  and comments, with **External Only** without the internal notes; or
  **Python Code** that builds the text itself. **Preview** shows it for a
  record.

The log notes the values each decision wrote.

To start an agent chat only where it is needed, put a decision in front of
the agent action: a **Yes/No Check** whose answer **yes** and **When Unsure**
both run the agent action.

A step of an AI automation rule (*MuK AI > Automation > Automation Rules*) is a
decision or an agent run: a decision step sets the tags of a new record, an
agent step after it works with them.

A module asks for a decision in Python::

    result = env['muk_ai.decision']._decide(
        mail.body,
        {
            'team': {
                'type': 'choice',
                'instructions': 'Which team should handle this?',
                'criteria': {'billing': 'Payments', 'support': 'Bugs'},
            },
            'refund': {'type': 'noul', 'instructions': 'Is it a refund request?'},
        },
        min_confidence=0.8,
        record=mail,
        origin='mail_triage',
    )

Each answer carries its confidence and a ``confident`` flag against
``min_confidence``. Pass ``model`` to pin one model version; a pinned model
never hands over to another provider.

AI agents call the ``decide`` tool about the texts they were given, the
records they name, or every record a domain selects; a question can name a field
to take its options from, and the result groups the texts or records by answer
with the value to write. Its cost counts against the budget of the chat. *MuK AI > Reports
> Decision Logs* lists every decision with its answers, served model version,
duration and cost.

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
