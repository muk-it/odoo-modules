DEFAULT_CONTEXT_WINDOW = 128000

MAX_ITERATIONS = 20
MAX_TOOL_CALLS_PER_ROUND = 10
MAX_WALLCLOCK_SECONDS = 600


class StreamCancelled(Exception):
    pass


def coerce_ids(values):
    ids = []
    for value in values or []:
        if isinstance(value, bool):
            continue
        if isinstance(value, int):
            ids.append(value)
            continue
        if isinstance(value, str):
            try:
                ids.append(int(value))
            except ValueError:
                continue
    return ids


def sanitize_json_schema(schema):
    if not isinstance(schema, dict):
        return schema
    cleaned = dict(schema)
    if cleaned.get('type') == 'array' and 'items' not in cleaned:
        cleaned['items'] = {}
    if isinstance(cleaned.get('items'), dict):
        cleaned['items'] = sanitize_json_schema(cleaned['items'])
    if isinstance(cleaned.get('properties'), dict):
        cleaned['properties'] = {
            name: sanitize_json_schema(value)
            for name, value in cleaned['properties'].items()
        }
    for key in ('anyOf', 'oneOf', 'allOf'):
        if isinstance(cleaned.get(key), list):
            cleaned[key] = [
                sanitize_json_schema(s) for s in cleaned[key]
            ]
    return cleaned
