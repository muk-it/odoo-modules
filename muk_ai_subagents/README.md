# MuK AI Subagents

Delegate work to focused subagent agents that run in parallel.

An agent can hand a task to another agent and carry on. Each subagent is a
session of its own, with its own context and its own agent
configuration — so the permission model is the one you already know.
One quiet line above the composer says what the subagents are doing,
every subagent is openable and keeps a permanent link, and a subagent that
starts repeating itself says so before it ends.

Requires `muk_ai`.

## Why delegate

A single agent answering _"which of our top 30 resellers are trending
down this quarter, and why?"_ has to read thirty accounts into one
context window and keep them all straight. Three subagents each reading
ten, and reporting a short summary back, is both faster and more
accurate — each one starts clean.

The rule the module is built around: **parallelise reads, serialise
writes.** Fan-out wins on breadth-first reading and loses on work that
has to compose into a single artifact, because two subagents make
conflicting unstated decisions. Delegation is offered for the first and
capped so it cannot quietly become the second.

## Permissions

A subagent is governed **exactly like the main agent**. The three
settings that already live on `muk_ai.agent` do all the work:

-   **Approval Mode** — _Ask on writes_ or _Never ask_, per agent, so a
    bookkeeping specialist and a research specialist can differ.
-   **Restrict to Read-only Tools** — available per agent if you want a
    particular subagent kept to reading. It is not imposed on subagents as a
    class; a subagent that cannot act tends to loop quietly rather than fail
    loudly.
-   **Tool Filter** — the exact tools that agent may call.

Two rules hold on top. A subagent's permissions are the **intersection**
with the conversation that spawned it — never the union. And **no
message from any agent counts as a human approval**; only a person
answers an approval card.

## Asking while you are looking elsewhere

A subagent that needs an approval or an answer would otherwise pause where
nobody can see it. Instead the question is raised **in the conversation
you are actually in**, labelled with the subagent's name and colour. The
buttons are the ones you already know:

-   **Approve once** — runs this call and records the decision.
-   **Allow for session** — auto-approves matching calls for the rest of
    _that subagent's_ session, so the grant cannot leak into your
    conversation or a sibling's.
-   **Reject** — hands the refusal back to the subagent, which re-plans and
    keeps working. Rejecting one action does not end the run.

## Configuration

**Agents — `MuK AI > Agents`**

-   **Allow Delegation** — lets this agent hand work to others.
-   **Delegates** — the agents it may delegate to. An agent can only
    delegate to something on this list.

**Settings — `Settings > General Settings > MuK AI`**

-   Concurrent subagents per run (default `5`).
-   Per-run budget, in the currency of the model's price list.
-   Stall timeout — how long a subagent may go quiet before it is flagged.

## Using it

Ask something that fans out. The agent calls `delegate` with one brief
per subagent: the objective, what success looks like, the shape of the
answer, and what is out of scope. Subagents start immediately and run at
the same time.

**In the chat** you get two compact cards: one line when the subagents
are spawned, and one card per subagent when it finishes — name, duration,
cost, its one-line answer, and a link to the full transcript. Subagent
tool calls never stream into the parent conversation.

**Above the composer** a single line stays in view for as long as the
run does: a dot per subagent, and the one thing worth knowing right now —
_"2 subagents working"_, _"Ada has been waiting 3m"_, _"1 subagent is
repeating itself"_. It says nothing at rest and it never covers the
conversation.

**Open that line** and the roster drops down, ordered by what needs you
first: waiting on you, stopped early, working, done. One row per subagent
— colour bar, name, what it is doing right now, elapsed. Finished rows
stay while anything is still running, then fold into a counted group;
a row that failed, and the row you have open, never fold.

**Open a row** and its detail opens under it, in place: the full
activity line, the question if it is blocked, its last few actions, its
cost, and buttons to open the transcript or stop it. Nothing floats and
nothing moves.

**Open the transcript** and you go to that subagent, the way you would
go to any other conversation: it takes the room the chat had, with a
breadcrumb back to the conversation that delegated it. Not a panel
beside the chat — a subagent is a session, not an attachment, and a
second conversation squeezed into half the width is unreadable on a
laptop and impossible in the 380px window. The same move works
everywhere: full page, floating window and phone, with nothing to
reflow and no breakpoint to get wrong.

**One composer, and it says whose it is.** It writes to whichever
conversation is on screen — the main agent while the chat is showing,
that subagent while its transcript is. The placeholder names the
subagent and when the message lands, and the send button shows the
queue clock, because that is what it does.

Every run keeps a permanent link and is collected in a **Subagents** space, so the chat sidebar stays as it was and old runs remain
reachable.

## Steering a subagent that is already running

A subagent used to be fire-and-forget: you wrote the brief, and the
only controls left were waiting and stopping. Now both you and the main
agent can change its direction while it works.

**You** open the subagent and type. The one composer is already addressing
it, and says so.

The main agent cannot redirect a subagent, and the honest reason is that it
has nothing to redirect _from_: it parks the moment the first subagent
starts and does not run again until every one of them has reported. A tool
for it would be a tool that never gets a turn to be called.

Nothing arrives mid-thought. A message is handed over **at the end of
the step the subagent is on**, so a tool call in flight always finishes
and nothing it has already done is lost. The answer to the main agent is
always `queued`, never `delivered`, because that is the only thing that
can honestly be promised.

Two guards: a subagent that has already reported cannot be steered — it
is asked again instead, on a turn of its own — and at most five messages
may wait for one subagent, so a main agent in a loop cannot flood it.

And when you redirect a subagent yourself, **the main agent is told**, in
its own transcript, as it happens. It is waiting on a brief it wrote; if
that brief changes underneath it, its final answer rests on a premise
that is no longer true. No other product surveyed does this, and in an
ERP it doubles as the audit trail.

## Not getting stuck

Repeating itself is the most common way a delegated agent fails, so the
runtime watches for it rather than trusting the prompt:

-   **Loop detection** fingerprints each action as the tool, its
    arguments, and a hash of the result. The same action with the _same_
    result three times is a loop; the same action with _changing_ results
    is ordinary work and is left alone. When it fires the subagent is first
    told plainly that it is repeating itself, then loses that tool for a
    couple of rounds, and only then is stopped.
-   **It says so while it happens.** A subagent that has started repeating
    itself is flagged on its row and on the line above the composer
    while it still has rounds left, not only in the post-mortem. The
    most common complaint about every agent product on the market is
    not that the agent was wrong but that nothing said it was going
    nowhere.
-   **Heartbeats** mark each round. A scheduled sweep flags a subagent
    whose worker has gone quiet, so a subagent that died mid-call cannot
    read as _working_ forever. A subagent merely queued behind a busy
    worker is waiting for capacity, not stalled, and is left alone.
-   **No circular waiting.** The parent never blocks on a subagent. A subagent
    that needs you parks itself and releases its worker, so the classic
    deadlock — parent waiting on subagent waiting on a human watching the
    parent — cannot form.
-   **Every ending is labelled** — finished, out of budget, no progress,
    hit the round limit, stalled, stopped by you. Anything that is not a
    clean finish is shown as a warning on the result card, because a
    summary that quietly omits _"I only got through 3 of the 12
    invoices"_ is the most dangerous thing this module could produce.

## Limits

-   **Five subagents at once** per run, and **one level deep** — a subagent
    cannot delegate further. At the limit the tool is simply not offered,
    rather than offered and refused.
-   The per-run budget covers the whole tree, and a subagent's deadline
    never outlives its parent's.
-   Delegation costs roughly an order of magnitude more than a plain
    turn. The running total is one click away in the roster, and only
    climbs onto the resting line once the run has spent four fifths of
    its budget — a meter in the corner of your eye makes people stop
    asking for things, which is not what it is there for.

## Installation

Download the module and add it to your Odoo addons folder. Log into
your Odoo server, open the Apps menu, enable developer mode, click
**Update Apps List**, and install **MuK AI Subagents**.

## Upgrade

Download the updated module, replace the folder in your addons path,
restart the server, open the Apps menu, find **MuK AI Subagents**, and
click Upgrade.

## Credits

**Contributors**

-   Mathias Markl &lt;mathias.markl@mukit.at&gt;

**Author &amp; Maintainer**

This module is maintained by [MuK IT GmbH](https://www.mukit.at/). MuK
IT is an Austrian company specialized in customizing and extending
Odoo. Contact: sale@mukit.at or https://mukit.at.
