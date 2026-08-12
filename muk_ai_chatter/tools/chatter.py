from __future__ import annotations

import re
from collections.abc import Callable

from markupsafe import Markup

CHATTER_SESSION_LIMIT = 10

RECORD_REF_RE = re.compile(r'\b(?P<model>[a-z_]+(?:\.[a-z_]+)+)[,/](?P<id>\d+)\b')


def fenced(tag: str, text: str) -> str:
    """Return ``text`` wrapped in ``<tag>`` with any closing tag it carries cut.

    The text comes from a draft or a chatter message, so it can hold the very
    tag used to fence it and end the block early, leaving the rest to read as
    instructions rather than as data.

    Cut until none is left rather than once: a single pass over
    ``</thread_</thread_context>context>`` leaves a whole closing tag behind,
    which is exactly what somebody writing into the thread would send.
    """
    closing = '</%s>' % tag
    body = text or ''
    while closing in body:
        body = body.replace(closing, '')
    return '<%s>\n%s\n</%s>' % (tag, body, tag)


def session_link(session_id: int, label: str) -> Markup:
    """Return a chatter link opening the given session."""
    return Markup(
        '<a href="/odoo/action-muk_ai.action_ai_session/{sid}">{label}</a>'
    ).format(sid=session_id, label=label)


def linkify_records(body: Markup, is_known_model: Callable[[str], bool]) -> Markup:
    """Turn the record references an answer mentions into links.

    An agent naming a record tends to spell it the way it reads it —
    ``res.partner,42`` or ``res.partner/42`` — which lands in the chatter as
    dead text. Unknown models are left alone, so prose that merely looks like
    a reference is never rewritten into a broken link.

    :param is_known_model: tells whether a model name exists in the registry
    """

    def replace(match) -> str:
        model, res_id = match.group('model'), match.group('id')
        if not is_known_model(model):
            return match.group(0)
        return str(
            Markup(
                '<a href="/odoo/{model}/{res_id}" class="o_mail_redirect" '
                'data-oe-model="{model}" data-oe-id="{res_id}">{label}</a>'
            ).format(model=model, res_id=res_id, label=match.group(0))
        )

    return Markup(RECORD_REF_RE.sub(replace, str(body)))
