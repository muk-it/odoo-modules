import logging

_logger = logging.getLogger(__name__)


LIST_MODELS_CODE = """
search_term = arguments.get('search', '').lower()
limit = arguments.get('limit', 100)
models_data = []
for model_name, model_cls in env.items():
    if search_term and search_term not in model_name.lower():
        continue
    description = getattr(model_cls, '_description', None) or model_name
    models_data.append({
        'model': model_name,
        'description': description,
    })
models_data.sort(key=lambda m: m['model'])
result = models_data[:limit]
"""


def migrate(cr, version):
    if not version:
        return
    cr.execute(
        """
        SELECT mmt.id, mmt.code
        FROM muk_mcp_tool mmt
        JOIN ir_model_data imd
          ON imd.model = 'muk_mcp.tool'
         AND imd.res_id = mmt.id
         AND imd.module = 'muk_mcp'
         AND imd.name = 'tool_list_models'
        """,
    )
    row = cr.fetchone()
    if not row:
        return
    tool_id, current_code = row
    if 'try:' not in (current_code or '') or 'getattr' in (current_code or ''):
        return
    cr.execute(
        'UPDATE muk_mcp_tool SET code = %s WHERE id = %s',
        (LIST_MODELS_CODE, tool_id),
    )
    _logger.info(
        'muk_mcp: rewrote tool_list_models code to avoid JUMP_BACKWARD_NO_INTERRUPT '
        'opcode rejected by safe_eval on Python 3.13',
    )
