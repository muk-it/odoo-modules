import json

TOOL_PREFIX = 'ee_action_'

CALLER_COMPONENT = 'mail_composer'

DEFAULT_RAG_TOP_N = 5
DEFAULT_RAG_DIMENSIONS = 1536
DEFAULT_EMBEDDING_MODEL = 'text-embedding-3-small'

EMPTY_SCHEMA = {'type': 'object', 'properties': {}}


def action_tool_name(action_id, xml_id):
    tech = xml_id.split('.', 1)[1] if xml_id and '.' in xml_id else f'action_{action_id}'
    return f'{TOOL_PREFIX}{tech}'


def coerce_schema(schema_text):
    if not schema_text:
        return dict(EMPTY_SCHEMA)
    try:
        schema = json.loads(schema_text)
    except (TypeError, ValueError):
        return dict(EMPTY_SCHEMA)
    if not isinstance(schema, dict):
        return dict(EMPTY_SCHEMA)
    schema.setdefault('type', 'object')
    schema.setdefault('properties', {})
    return schema


def serialize_result(result):
    if result is None or isinstance(result, str):
        return result or ''
    try:
        return json.dumps(result, default=str)
    except (TypeError, ValueError):
        return str(result)


def render_init_context(view_context):
    if not isinstance(view_context, dict):
        return ''
    items = view_context.get('ee_init_context') or []
    if not items:
        return ''
    body = '\n'.join(items)
    return f'<ee_ctx>\n{body}\n</ee_ctx>'
