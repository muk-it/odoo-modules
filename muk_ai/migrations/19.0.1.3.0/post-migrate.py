from odoo.tools import create_index


def migrate(cr, version):
    if not version:
        return
    create_index(
        cr,
        'muk_mcp_log_session_id_create_date_idx',
        'muk_mcp_log',
        ['session_id', 'create_date'],
    )
    create_index(
        cr,
        'muk_ai_session_user_id_create_date_idx',
        'muk_ai_session',
        ['user_id', 'create_date'],
    )
