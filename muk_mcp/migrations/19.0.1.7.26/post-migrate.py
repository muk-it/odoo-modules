from __future__ import annotations

from odoo import SUPERUSER_ID, api


def migrate(cr, version: str) -> None:
    """Wrap the ``post_message`` tool body in ``Markup`` on existing databases.

    The tool record is ``noupdate``, so the shipped code fix never reaches
    installed instances. Without a ``Markup`` object ``message_post`` escapes a
    plain ``str`` body, and any HTML posted through the tool renders as literal
    ``<p>``/``<br>`` tags. Patch the stored code in place, replacing only the
    exact old snippet so customized tool bodies are left untouched.
    """
    env = api.Environment(cr, SUPERUSER_ID, {})
    tool = env.ref('muk_mcp.tool_post_message', raise_if_not_found=False)
    if tool and 'body=body,' in (tool.code or ''):
        tool.code = tool.code.replace('body=body,', 'body=Markup(body),')
