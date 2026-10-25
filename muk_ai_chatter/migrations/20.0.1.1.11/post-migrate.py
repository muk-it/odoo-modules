from __future__ import annotations

from odoo import SUPERUSER_ID, api
from odoo.sql_db import Cursor


def migrate(cr: Cursor, version: str | None) -> None:
    """Give the writing helpers icons the icon font draws, unless changed by hand."""
    env = api.Environment(cr, SUPERUSER_ID, {})
    for xmlid, old, new in (
        ('skill_compose_grammar', 'spellcheck', 'check'),
        ('skill_compose_formal', 'business_center', 'work'),
    ):
        skill = env.ref(f'muk_ai_chatter.{xmlid}', raise_if_not_found=False)
        if skill and skill.icon == old:
            skill.icon = new
