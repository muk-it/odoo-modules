from __future__ import annotations

from .chatter import fenced

# ----------------------------------------------------------
# Composer Surfaces
# ----------------------------------------------------------

COMPOSE_INTERFACES = [
    ('text_select', 'Rewriting a Selection'),
    ('mail_composer', 'Writing a Message'),
    ('html_field', 'Writing in a Field'),
]

COMPOSE_MAX_CHARS = 12000

# ----------------------------------------------------------
# Selection Marks
# ----------------------------------------------------------

SELECTION_OPEN = '[['

SELECTION_CLOSE = ']]'

# ----------------------------------------------------------
# Prompt Scaffolding
# ----------------------------------------------------------

COMPOSE_RULES = (
    '<compose_rules>\n'
    'You are writing on behalf of the user, in the composer they are typing '
    'in. What you reply is dropped into that composer exactly as it stands, '
    'so reply with the message text and nothing else: no preamble, no title '
    'or header line, no closing remark of your own, no explanation of what '
    'you changed, and no quotation marks around the whole answer. Never write '
    'a model and id such as res.partner,42 — the reader is already on that '
    'record; use its name, or say "this record". Keep the language the user '
    'is writing in. Sign nothing and invent nothing — every fact must come '
    'from the draft, the conversation or the record. Nobody can answer a '
    'question here, so never call ask_user: if something is missing, write '
    'the message with a clearly marked gap the user can fill in.\n'
    '</compose_rules>'
)

COMPOSE_TURN_REMINDER = (
    '%s\n\n---\n'
    'Answer with the message text itself, ready to send. Not a report of what '
    'you drafted, not a title, not a model and id, not a note about the '
    'composer — the words that go in the message, and nothing else.'
)

COMPOSE_SELECTION_RULES = (
    'Rewrite the selected part only. The draft is shown with that part marked '
    'between %(open)s and %(close)s: what you return is pasted between the '
    'words before and after those marks, so read them first and make it fit '
    'there. Match what the selection is — if it does not start a sentence, do '
    'not start one; if it does not end a sentence, do not end with a full '
    'stop; if it continues a clause, continue it. Never repeat the words '
    'around it, never write the marks, and return the replacement alone.'
) % {'open': SELECTION_OPEN, 'close': SELECTION_CLOSE}


def compose_text_values(draft: str | None, selection: str | None) -> dict:
    """Return the draft and the selected part as a session stores them."""
    return {
        'compose_draft': (draft or '')[:COMPOSE_MAX_CHARS],
        'compose_selection': (selection or '')[:COMPOSE_MAX_CHARS],
    }


def mark_selection(draft: str, selection: str) -> str:
    """Return ``draft`` with the part to rewrite marked where it sits.

    A selection handed over on its own leaves the agent to guess what comes
    before and after it, and it answers with a whole sentence where a fragment
    belongs — ``I'll`` followed by ``Please prepare a quote.`` Shown in place,
    the gap it has to fill is not a guess.
    """
    if not selection or not draft or selection not in draft:
        return ''
    return draft.replace(selection, f'{SELECTION_OPEN}{selection}{SELECTION_CLOSE}', 1)


def compose_addenda(draft: str, selection: str) -> list[str]:
    """Return what the agent is told about the composer it writes in."""
    addenda = [COMPOSE_RULES]
    if selection:
        addenda.append(COMPOSE_SELECTION_RULES)
        addenda.append(fenced('selected_text', selection))
    if marked := mark_selection(draft, selection):
        addenda.append(fenced('draft_with_selection', marked))
    elif draft:
        addenda.append(fenced('draft', draft))
    return addenda
