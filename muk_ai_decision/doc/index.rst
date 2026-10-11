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
actions and flags unsure ones from any automation rule or scheduled action, an
agent action can run only for the records a yes/no gate lets through, and
agents decide about texts or records through the decide tool.

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
  Two accounts ship archived: *typesafe* decides with *Jev* in the TypeSafe
  cloud once its API key is set, *decis* with *Laya* on a self-hosted Decis
  server at its **Custom URL**, which needs a key only when the server asks
  for one. Activate the one you use; **Test Connection** answers one question.
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

- **Questions**: each fills a **Target Field**, whose values are the options: a
  selection, the **Candidates** of a many2one, one yes/no per tag of a tags
  field, or a yes/no field. A question without a target field lists its own
  options. An answer is written only above its **Min. Confidence**; tags are
  only added, never removed.
- **Route Answer** and **Run Action**: run another server action on all
  records answered that way, for example an AI agent action for complaints.
- **When Unsure**: an action run on the records with an answer below its
  confidence, for example one that schedules an activity to check them.
- **Reads**: the fields the decision model reads, by default the name and the
  text fields, and with **Read Last Message** the last email or comment.
- **Shadow Mode**: decide and log only, to try a configuration before it writes.

The log notes the values each decision wrote, or would have written in
shadow mode.

On a **Run AI Agent** action, **Run Only When** asks a yes/no question about
each record first: only the records confidently answered no are skipped, so an
agent chat starts only where it is needed.

A module asks for a decision in Python::

    result = env['muk_ai.decision'].decide(
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
> Decisions* lists every decision with its answers, served model version,
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
