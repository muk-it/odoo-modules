from __future__ import annotations

from odoo import SUPERUSER_ID, api
from odoo.sql_db import Cursor

REPAIRS = (
    (
        'muk_ai_skills.skill_reply',
        'body',
        (
            (
                '1. Resolve the target record from the pinned record in `<ui_ctx>` (model + id). If still missing,',
                (
                    '1. Take the target record (model + id) from `<ui_ctx>`, or from `<linked_record>` when the\n'
                    '   session was started from a record. If neither names one,'
                ),
            ),
        ),
    ),
    (
        'muk_ai_skills.demo_skill_log',
        'body',
        (
            (
                (
                    '1. Resolve the target record from the pinned record in `<ui_ctx>` (model + id). If still\n'
                    '   missing, call `ask_user` once for a record reference.'
                ),
                (
                    '1. Take the target record (model + id) from `<ui_ctx>`, or from `<linked_record>` when the\n'
                    '   session was started from a record. If neither names one, call `ask_user` once for a\n'
                    '   record reference.'
                ),
            ),
            (
                (
                    '3. Wrap the text as minimal HTML — `<p>…</p>` paragraphs only. No styles, no signature.\n'
                    '4. Call `call_method`:'
                ),
                '3. Call `call_method`:',
            ),
            (
                '     - `body`: the HTML',
                (
                    "     - `body`: the user's text as plain text — `message_post` escapes strings, so HTML tags\n"
                    '       would show up literally in the note'
                ),
            ),
            (
                '5. Reply with one short confirmation line, e.g. `Logged on <display_name>.` Stop. Do not open',
                '4. Reply with one short confirmation line, e.g. `Logged on <display_name>.` Stop. Do not open',
            ),
        ),
    ),
)


def migrate(cr: Cursor, version: str) -> None:
    """Repair the shipped skills where they described calls that misfire.

    These records ship ``noupdate="1"``, so a corrected data file never reaches
    a database that already carries them. Each fragment is rewritten only where
    it still reads exactly as shipped, leaving a prompt somebody has since
    edited untouched.
    """
    env = api.Environment(cr, SUPERUSER_ID, {})
    for xmlid, field, replacements in REPAIRS:
        record = env.ref(xmlid, raise_if_not_found=False)
        if not record:
            continue
        text = record[field] or ''
        for old, new in replacements:
            text = text.replace(old, new)
        if text != record[field]:
            record[field] = text
