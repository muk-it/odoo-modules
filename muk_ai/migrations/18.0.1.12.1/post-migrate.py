from __future__ import annotations

import os

from lxml import etree

from odoo import SUPERUSER_ID, api
from odoo.sql_db import Cursor


def migrate(cr: Cursor, version: str) -> None:
    """Refresh the noupdate General Assistant prompt from XML on upgrade.

    ``agent_general`` lives in a ``noupdate="1"`` block, so the loader skips
    it on upgrade and the improved system prompt (Trust/hierarchy, batching,
    anti-non-answer, Odoo terms) never reaches existing databases. Re-read the
    shipped value from the data file and write it directly. A local
    customization of this shipped agent's prompt is overwritten.
    """
    env = api.Environment(cr, SUPERUSER_ID, {})
    record = env.ref('muk_ai.agent_general', raise_if_not_found=False)
    if not record:
        return
    path = os.path.join(os.path.dirname(__file__), '..', '..', 'data', 'agent.xml')
    tree = etree.parse(path)  # noqa: S320 -- trusted in-repo data file
    nodes = tree.xpath("//record[@id='agent_general']/field[@name='system_prompt']")
    if nodes and nodes[0].text is not None:
        record.system_prompt = nodes[0].text
