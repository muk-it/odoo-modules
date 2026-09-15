from __future__ import annotations

from lxml import etree

from odoo import SUPERUSER_ID, api
from odoo.sql_db import Cursor
from odoo.tools import file_open


def migrate(cr: Cursor, version: str) -> None:
    """Refresh the shipped prompt of the general agent, unless a person edited it.

    ``data/agent.xml`` is ``noupdate``, so a database that already carries the
    record keeps the prompt it was created with and would never see the
    handoff, decline and stop rules this release adds. The new text is read
    back out of that same file instead of being copied in here, so the two
    cannot drift apart.

    The prompt belongs to whoever last wrote it: a revision authored by a real
    user means the text is theirs, and the record is left alone. The revision
    this migration leaves behind is authored by the superuser, so upgrading a
    second time still refreshes a prompt nobody has touched.
    """
    env = api.Environment(cr, SUPERUSER_ID, {})
    agent = env.ref('muk_ai.agent_general', raise_if_not_found=False)
    if not agent:
        return
    revisions = (agent.prompt_history or {}).get('system_prompt') or []
    if any(entry.get('create_uid') != SUPERUSER_ID for entry in revisions):
        return
    with file_open('muk_ai/data/agent.xml', 'rb') as data_file:
        tree = etree.parse(data_file)
    node = tree.find('.//record[@id="agent_general"]/field[@name="system_prompt"]')
    if node is not None and node.text:
        agent.system_prompt = node.text
