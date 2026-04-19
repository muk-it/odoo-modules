import json


def _build_method_index(env):
    index = {}
    for anchor in ('muk_mcp.mixin',):
        Model = env.registry.get(anchor)
        if Model is None:
            continue
        seen = set()
        for klass in Model.mro():
            for attr_name, attr in vars(klass).items():
                if attr_name.startswith('__') or attr_name in seen:
                    continue
                meta = getattr(attr, '__mcp_tool__', None)
                if not meta or not isinstance(meta, dict):
                    continue
                seen.add(attr_name)
                name = meta['name']
                if name in index:
                    prev = index[name]
                    raise ValueError(
                        "Duplicate @mcp_tool name %r: declared on %s.%s and %s.%s" % (
                            name, anchor, attr_name, prev['model'], prev['method']
                        )
                    )
                index[name] = {
                    'kind': 'method',
                    'model': anchor,
                    'method': attr_name,
                    'description': meta['description'],
                    'input_schema': meta['input_schema'],
                    'category': meta['category'],
                }
    return index


def _fetch_db_index(env):
    index = {}
    records = env['muk_mcp.tool'].sudo().search_read(
        [('active', '=', True)],
        fields=['id', 'name', 'description', 'input_schema', 'category'],
    )
    for record in records:
        raw_schema = record.get('input_schema')
        schema = json.loads(raw_schema) if raw_schema else {
            'type': 'object',
            'properties': {},
        }
        index[record['name']] = {
            'kind': 'db',
            'id': record['id'],
            'description': record['description'],
            'input_schema': schema,
            'category': record['category'],
        }
    return index


def mcp_tool(name=None, description=None, input_schema=None, category='read'):
    def decorator(func):
        func.__mcp_tool__ = {
            'name': name or func.__name__,
            'description': (
                description
                or (func.__doc__ or '').strip().split('\n')[0]
                or func.__name__
            ),
            'input_schema': input_schema or {
                'type': 'object',
                'properties': {},
            },
            'category': category,
        }
        return func
    return decorator


def get_tool_index(env):
    method_index = getattr(env.registry, '_muk_mcp_method_cache', None)
    if method_index is None:
        method_index = _build_method_index(env)
        env.registry._muk_mcp_method_cache = method_index
    db_index = _fetch_db_index(env)
    if not db_index:
        return method_index
    return {**method_index, **db_index}


def invalidate_registry_cache(env):
    if hasattr(env.registry, '_muk_mcp_method_cache'):
        del env.registry._muk_mcp_method_cache
