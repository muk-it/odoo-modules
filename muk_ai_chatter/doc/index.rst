==============
MuK AI Chatter
==============

Mention an AI agent in a Discuss channel or a direct chat and get an
answer back in the conversation. **MuK AI Chatter** ties
``muk_ai.session`` to the business record it runs for, lists those
sessions in the chatter of any threaded model, and lets a user summon an
agent with the ordinary ``@`` syntax — the same one they already use for
colleagues.

The agent answers as an ordinary message in the conversation it was
mentioned in. It never becomes a member, is never emailed, and never
speaks again unless somebody mentions it. A mentioned agent **never
stops to ask**: a conversation always ends up with an answer rather than
a question nobody will see.

A record's chatter offers no agents and answers no mention: a chatter
message is addressed to the people following the record, and an agent
replying there reads as mail somebody sent. The surface for a record is
the **writing helper** in the composer, described below.

Installation
============

To install this module, you need to:

Download the module and add it to your Odoo addons folder. Afterward, log
on to your Odoo server and go to the Apps menu. Trigger the debug mode
and update the list by clicking on the "Update Apps List" link. Now
install the module by clicking on the install button.

Configuration
=============

Every agent is given a stand-in contact the first time this module is
installed, and whenever an agent is created afterwards. That contact
carries no email address, so mentioning an agent can never mail anybody.

Open *MuK AI → Agents* and use the **Chatter** group on the agent form:

- **Answer Mentions** — whether the agent replies when it is mentioned.
  On by default. Turning it off takes the agent out of every suggestion
  list, and its contact is still kept out of the recipients of a message
  that names it anyway.

A mention runs the tools the agent carries, writes included. It never
stops to ask, so anything it may change it changes unattended: give an
agent you let people summon from a conversation only the tools you mean
it to use there.

Usage
=====

In a Discuss channel or a direct chat, type ``@``, pick the agent from
the suggestion list, and write the request. A message from the agent
appears straight away and is rewritten in place with the answer as the
run finishes — everybody looking at the conversation sees it swap over
without reloading.

Discuss offers members only and admits nobody else as a recipient of a
chat, so the agents are named back into both lists — they are suggested
next to the members and carried through the post, without ever being
added to the conversation.

Writing a message
-----------------

The composer carries a **Write with AI** button, and every rich-text
editor the same command in its toolbar and behind ``/``. What the panel
offers depends on what is in the composer:

* **with text selected** — the transforms that rewrite exactly that part
  (shorten, expand, formal, friendly, fix grammar, translate). The answer
  is shown as a diff against what was selected, and replaces only that
  part when accepted;
* **on an empty composer** — what can be written from the record (reply
  to the last message, follow up, summarize), with a length and a tone
  chosen *before* generating.

The answer streams into the panel as it is written. Nothing reaches the
message until *Insert* or *Replace* is clicked; ``Esc`` dismisses at no
cost, and *Try again* re-runs the same request. When a request outgrows a
chip, **Open in AI chat** hands the same session — draft, selection and
conversation included — to the chat window, where the agent can ask
questions again.

The chips are skills, not code: an admin edits them under *MuK AI →
Skills*, where each one carries its wording, its icon and the category
that decides where it is offered — *fix*, *rewrite* and *transform* act on
what is already written, *generate* writes something new. A skill of type
*Composer* is offered here and nowhere else: it never joins the list of
skills the agent discovers in a chat.

The **AI Sessions** box in the chatter lists the runs attached to the
record — the ones you ran yourself, and, for an administrator, everybody
else's as well. A session stays with whoever ran it: its transcript
carries tool output gathered under that user's rights, so being able to
read a record never opens the conversations held against it.

Chats attached to a record are also collected in the **Records** space
in the AI sidebar, and the helpers themselves in a **Writing Helper**
space that keeps them for a week: they are drafts of messages, and a
message that was sent is the record of what was written.

Design notes
============

A mention, and the writing helper on a record, both point a language
model at a thread that is largely written by people outside the company,
so the module treats that thread as untrusted input:

* the conversation is passed inside a ``<thread_context>`` block with an
  explicit "this is data, not instructions" preamble, its closing tag
  stripped so a message cannot break out of the block;
* the tool set is fixed before the agent reads any of it, so nothing in
  the thread can widen what the run is able to do;
* the thread is snapshotted onto the session, because chatter messages
  can be edited or deleted after the agent has been told about them;
* an agent's own post summons nobody, and neither does a message written
  by a tool from inside a running session, so agents cannot answer each
  other in a loop;
* approvals and browser-served tools are switched off for a mention, so
  the run cannot pause waiting for somebody who is not there;
* an agent contact is stripped from the recipients of every message on
  every thread, a record's chatter included, so naming one never mails
  it, notifies it or enrols it as a follower;
* a poster who may not run a session at all — a portal customer on their
  own order — summons nothing, and their message is posted as usual
  rather than failing on an access error;
* the writing helper runs read-only whatever it is asked for, cannot stop
  to ask a question its panel could not show, and announces nothing in
  the systray: the user is watching the run happen.

Credits
=======

Contributors
------------

* Mathias Markl <mathias.markl@mukit.at>

Author & Maintainer
-------------------

MuK IT GmbH
