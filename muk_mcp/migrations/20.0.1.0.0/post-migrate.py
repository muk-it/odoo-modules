from __future__ import annotations

from odoo.sql_db import Cursor

OLD_FIELDS = """        result = env['mail.message'].search_read(
            [('model', '=', model_name), ('res_id', '=', record_id)],
            fields=[
                'date', 'author_id', 'message_type', 'subtype_id',
                'body', 'tracking_value_ids',
            ],
"""

NEW_FIELDS = """        fields = ['date', 'author_id', 'message_type', 'subtype_id', 'body']
        fields += list(env['mail.message'].fields_get(['tracking_value_ids']))
        result = env['mail.message'].search_read(
            [('model', '=', model_name), ('res_id', '=', record_id)],
            fields=fields,
"""


def migrate(cr: Cursor, version: str | None) -> None:
    """Read tracking values in ``get_messages`` only where ``mail_tracking`` adds them."""
    cr.execute(
        """
        UPDATE muk_mcp_tool
           SET code = replace(code, %(old)s, %(new)s)
         WHERE position(%(old)s IN code) > 0
           AND id = (
               SELECT res_id FROM ir_model_data
                WHERE module = 'muk_mcp'
                  AND name = 'tool_get_messages'
           )
        """,
        {'old': OLD_FIELDS, 'new': NEW_FIELDS},
    )
