import json

from odoo.addons.muk_mcp.tools.schema import to_strict_schema


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
                    'registry': meta['registry'],
                }
    return index


def _fetch_db_index(env):
    index = {}
    records = env['muk_mcp.tool'].sudo().search_read(
        [('active', '=', True)],
        fields=['id', 'name', 'description', 'input_schema', 'category', 'registry'],
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
            'registry': record.get('registry') or None,
        }
    return index


def mcp_tool(
    name=None,
    description=None,
    input_schema=None,
    category='read',
    registry=None,
):
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
            'registry': registry,
        }
        return func
    return decorator


def get_tool_index(env, registry=None):
    cache_key = len(getattr(env.registry, '_init_modules', None) or ())
    method_index = getattr(env.registry, '_muk_mcp_method_cache', None)
    cached_key = getattr(env.registry, '_muk_mcp_method_cache_key', None)
    stale = (
        method_index is None
        or (cached_key is not None and cached_key != cache_key)
    )
    if stale:
        method_index = _build_method_index(env)
        env.registry._muk_mcp_method_cache = method_index
        env.registry._muk_mcp_method_cache_key = cache_key
    db_index = _fetch_db_index(env)
    combined = (
        {**method_index, **db_index}
        if db_index else dict(method_index)
    )
    if registry is not None:
        combined = {
            name: entry for name, entry in combined.items()
            if not entry.get('registry') or registry in (
                s.strip() for s in entry['registry'].split(',')
            )
        }
    return {
        name: {
            **entry,
            'input_schema': to_strict_schema(entry.get('input_schema')),
        }
        for name, entry in combined.items()
    }


def invalidate_registry_cache(env):
    if hasattr(env.registry, '_muk_mcp_method_cache'):
        del env.registry._muk_mcp_method_cache
    if hasattr(env.registry, '_muk_mcp_method_cache_key'):
        del env.registry._muk_mcp_method_cache_key
