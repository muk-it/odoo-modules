import logging

_logger = logging.getLogger(__name__)


TOOL_XMLID_RENAMES = (
    ('tool_get_record_messages', 'tool_get_messages', 'get_messages'),
)


def migrate(cr, version):
    if not version:
        return
    for old_xmlid, new_xmlid, new_name in TOOL_XMLID_RENAMES:
        cr.execute(
            """
            UPDATE ir_model_data
               SET name = %s
             WHERE module = 'muk_mcp'
               AND model = 'muk_mcp.tool'
               AND name = %s
            """,
            (new_xmlid, old_xmlid),
        )
        cr.execute(
            """
            UPDATE muk_mcp_tool
               SET name = %s
             WHERE id = (
                 SELECT res_id FROM ir_model_data
                 WHERE module = 'muk_mcp'
                   AND model = 'muk_mcp.tool'
                   AND name = %s
             )
            """,
            (new_name, new_xmlid),
        )
    _logger.info(
        'muk_mcp: renamed DB tools for v19.0.1.4.1: %s',
        ', '.join(f'{old} -> {new}' for old, new, _n in TOOL_XMLID_RENAMES),
    )
