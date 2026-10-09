from __future__ import annotations

import re
from collections.abc import Callable

from markupsafe import Markup

CHATTER_SESSION_LIMIT = 10

PLAIN_TEXT_RULE = (
    'Your answer is shown as plain text: write no Markdown, no headings, no '
    'bold, no tables and no [label](target) links; a list is lines starting '
    'with a dash.'
)

RECORD_REF_RE = re.compile(r'\b(?P<model>[a-z_]+(?:\.[a-z_]+)+)[,/](?P<id>\d+)\b')


def fenced(tag: str, text: str) -> str:
    """Return ``text`` wrapped in ``<tag>``, every closing tag it carries cut.

    The cut repeats until none is left, so a nested closing tag such as
    ``</thread_</thread_context>context>`` cannot end the block early.
    """
    closing = '</%s>' % tag
    body = text or ''
    while closing in body:
        body = body.replace(closing, '')
    return '<%s>\n%s\n</%s>' % (tag, body, tag)


def session_link(session_id: int, label: str) -> Markup:
    """Return a chatter link opening the given session."""
    return Markup('<a href="/odoo/ai-sessions/{sid}">{label}</a>').format(
        sid=session_id, label=label
    )


def linkify_records(body: Markup, is_known_model: Callable[[str], bool]) -> Markup:
    """Turn the ``model,id`` and ``model/id`` references of an answer into links.

    :param is_known_model: tells whether a model name exists in the registry
    """

    def replace(match: re.Match) -> str:
        """Return the link for one reference, or the reference itself."""
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
