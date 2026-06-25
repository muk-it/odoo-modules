import logging

_logger = logging.getLogger(__name__)


PORTED_TOOL_XMLIDS = (
    'tool_list_modules',
    'tool_list_models',
    'tool_get_model_schema',
    'tool_search_read',
    'tool_read',
    'tool_search_count',
    'tool_create',
    'tool_write',
    'tool_unlink',
    'tool_get_user_context',
    'tool_get_access_rights',
    'tool_read_group',
    'tool_call',
)


def migrate(cr, version):
    if not version:
        return
    cr.execute(
        """
        SELECT imd.res_id, imd.name
        FROM ir_model_data imd
        WHERE imd.module = 'muk_mcp'
          AND imd.model = 'muk_mcp.tool'
          AND imd.name IN %s
        """,
        (PORTED_TOOL_XMLIDS,),
    )
    rows = cr.fetchall()
    if not rows:
        return
    tool_ids = [row[0] for row in rows]
    cr.execute(
        'DELETE FROM muk_mcp_tool WHERE id IN %s',
        (tuple(tool_ids),),
    )
    cr.execute(
        """
        DELETE FROM ir_model_data
        WHERE module = 'muk_mcp'
          AND model = 'muk_mcp.tool'
          AND name IN %s
        """,
        (PORTED_TOOL_XMLIDS,),
    )
    _logger.info(
        'muk_mcp: removed %d DB tool records superseded by @mcp_tool Python methods: %s',
        len(rows),
        ', '.join(sorted(name for _id, name in rows)),
    )
