from __future__ import annotations

from odoo import models

from odoo.addons.muk_ai_chatter.tools.chatter import PLAIN_TEXT_RULE, fenced

COMPOSE_INTERFACES = [
    ('text_select', 'Rewriting a Selection'),
    ('mail_composer', 'Writing a Message'),
    ('html_field', 'Writing in a Field'),
]

COMPOSE_MAX_CHARS = 120000

SELECTION_OPEN = '[['

SELECTION_CLOSE = ']]'

COMPOSE_RULES = (
    '<compose_rules>\n'
    'You are writing on behalf of the user, in the composer they are typing '
    'in. What you reply is dropped into that composer exactly as it stands, '
    'so reply with the message text and nothing else: no preamble, no title '
    'or header line, no closing remark of your own, no explanation of what '
    'you changed, and no quotation marks around the whole answer. Never write '
    'a model and id such as res.partner,42: the reader is already on that '
    'record, so use its name, or say "this record". Keep the language the '
    'user is writing in. Sign nothing and invent nothing: every fact must '
    'come from the draft, the conversation or the record. Nobody can answer a '
    'question here, so never call ask_user. If something is missing, write '
    'the message with a clearly marked gap the user can fill in. '
    '%s\n'
    '</compose_rules>'
)

HTML_RULE = (
    'Your answer is an HTML fragment that is inserted into a rich-text editor as '
    'it stands: no html, head or body wrapper and no code fence. The draft is '
    'shown as HTML too: keep every tag, attribute, class and inline style of it '
    'that you are not asked to change.'
)

COMPOSE_TURN_REMINDER = {
    'role': 'user',
    'content': [
        {
            'type': 'input_text',
            'text': (
                '<compose_reminder>Answer with the message text itself, ready '
                'to send. Not a report of what you drafted, not a title, not a '
                'model and id, not a note about the composer: the words that go '
                'in the message, and nothing else.</compose_reminder>'
            ),
        }
    ],
    '_cache_volatile': True,
}

COMPOSE_SELECTION_RULES = (
    'Rewrite the selected part only. The draft is shown with that part marked '
    'between %(open)s and %(close)s: what you return is pasted between the '
    'words before and after those marks, so read them first and make it fit '
    'there. Match what the selection is: if it does not start a sentence, do '
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


def compose_addenda(session: models.BaseModel) -> list[str]:
    """Return what a writing helper is told about the composer it writes in."""
    plain = session.compose_interface == 'mail_composer'
    addenda = [COMPOSE_RULES % (PLAIN_TEXT_RULE if plain else HTML_RULE)]
    if selection := session.compose_selection:
        addenda.append(COMPOSE_SELECTION_RULES)
        addenda.append(fenced('selected_text', selection))
    if session.compose_draft:
        addenda.append(fenced('draft', session.compose_draft))
    return addenda
