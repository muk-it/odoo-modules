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
