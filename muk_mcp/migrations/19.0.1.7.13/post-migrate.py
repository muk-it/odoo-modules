from __future__ import annotations

from odoo.tools.sql import column_exists, table_exists


def migrate(cr, version: str) -> None:
    """Backfill the key snapshot from the old ``key_id`` relation, then drop it.

    Until this version the audit log referenced the API key through a
    ``key_id`` Many2one into the ``_auto = False`` ``muk_mcp.key`` table. Odoo
    never created its foreign key, so deleting a key left dangling references
    that made the log unreadable. The key identity is now snapshotted as text
    (``key_name`` / ``key_prefix``); copy it across from surviving keys and
    drop the obsolete relational column. Rows whose key was already deleted
    keep a null snapshot (that identity is unrecoverable).
    """
    if not column_exists(cr, 'muk_mcp_log', 'key_id'):
        return
    if table_exists(cr, 'muk_mcp_key'):
        if column_exists(cr, 'muk_mcp_key', 'key_prefix'):
            cr.execute(
                """
                UPDATE muk_mcp_log AS l
                SET key_name = k.name, key_prefix = k.key_prefix
                FROM muk_mcp_key AS k
                WHERE l.key_id = k.id
                """
            )
        else:
            cr.execute(
                """
                UPDATE muk_mcp_log AS l
                SET key_name = k.name
                FROM muk_mcp_key AS k
                WHERE l.key_id = k.id
                """
            )
    cr.execute('ALTER TABLE muk_mcp_log DROP COLUMN key_id')
