from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from odoo.api import Environment

from odoo.addons.muk_mcp.tools.schema import to_strict_schema


def _build_method_index(env: Environment) -> dict[str, dict[str, Any]]:
    """Scan the ``muk_mcp.mixin`` MRO for ``@mcp_tool`` methods, keyed by tool name.

    :raise ValueError: when two methods declare the same tool name.
    """
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
                tool_def = getattr(attr, '__mcp_tool__', None)
                if not tool_def or not isinstance(tool_def, dict):
                    continue
                seen.add(attr_name)
                name = tool_def['name']
                if name in index:
                    prev = index[name]
                    raise ValueError(
                        'Duplicate @mcp_tool name %r: declared on %s.%s and %s.%s'
                        % (
                            name,
                            anchor,
                            attr_name,
                            prev['model'],
                            prev['method'],
                        ),
                    )
                index[name] = {
                    'kind': 'method',
                    'model': anchor,
                    'method': attr_name,
                    'description': tool_def['description'],
                    'input_schema': tool_def['input_schema'],
                    'category': tool_def['category'],
                    'registry': tool_def['registry'],
                    'meta': tool_def.get('meta') or {},
                }
    return index


def _fetch_db_index(env: Environment) -> dict[str, dict[str, Any]]:
    """Load active ``muk_mcp.tool`` records into a name-keyed index."""
    index = {}
    records = (
        env['muk_mcp.tool']
        .sudo()
        .search_read(
            [('active', '=', True)],
            fields=[
                'id',
                'name',
                'description',
                'input_schema',
                'category',
                'registry',
            ],
        )
    )
    for record in records:
        raw_schema = record.get('input_schema')
        schema = (
            json.loads(raw_schema)
            if raw_schema
            else {
                'type': 'object',
                'properties': {},
            }
        )
        index[record['name']] = {
            'kind': 'db',
            'id': record['id'],
            'description': record['description'],
            'input_schema': schema,
            'category': record['category'],
            'registry': record.get('registry') or None,
            'meta': {},
        }
    return index


def mcp_tool(
    name: str | None = None,
    description: str | None = None,
    input_schema: dict[str, Any] | None = None,
    category: str = 'read',
    registry: str | None = None,
    meta: dict[str, Any] | None = None,
    visibility: list[str] | None = None,
) -> Callable:
    """Mark a mixin method as an MCP tool, defaulting metadata from the function."""

    def decorator(func: Callable) -> Callable:
        """Stamp the tool metadata onto the function and return it unchanged."""
        merged_meta = dict(meta or {})
        if visibility is not None:
            ui = dict(merged_meta.get('ui') or {})
            ui['visibility'] = list(visibility)
            merged_meta['ui'] = ui
        func.__mcp_tool__ = {
            'name': name or func.__name__,
            'description': (
                description
                or (func.__doc__ or '').strip().split('\n')[0]
                or func.__name__
            ),
            'input_schema': input_schema
            or {
                'type': 'object',
                'properties': {},
            },
            'category': category,
            'registry': registry,
            'meta': merged_meta,
        }
        return func

    return decorator


def get_tool_index(
    env: Environment, registry: str | None = None
) -> dict[str, dict[str, Any]]:
    """Return the merged tool index, caching the method scan and applying strict schemas.

    :param registry: optional registry name; keeps only tools with no registry or one
        whose comma-separated list contains it.
    :return: tool definitions keyed by name, DB tools overriding method tools.
    """
    cache_key = len(getattr(env.registry, '_init_modules', None) or ())
    method_index = getattr(env.registry, '_muk_mcp_method_cache', None)
    cached_key = getattr(env.registry, '_muk_mcp_method_cache_key', None)
    stale = method_index is None or (cached_key is not None and cached_key != cache_key)
    if stale:
        method_index = _build_method_index(env)
        env.registry._muk_mcp_method_cache = method_index
        env.registry._muk_mcp_method_cache_key = cache_key
    db_index = _fetch_db_index(env)
    combined = {**method_index, **db_index} if db_index else dict(method_index)
    if registry is not None:
        combined = {
            name: entry
            for name, entry in combined.items()
            if not entry.get('registry')
            or registry in (s.strip() for s in entry['registry'].split(','))
        }
    return {
        name: {
            **entry,
            'input_schema': to_strict_schema(entry.get('input_schema')),
            'meta': entry.get('meta') or {},
        }
        for name, entry in combined.items()
    }


def invalidate_registry_cache(env: Environment) -> None:
    """Drop the cached method tool index so it is rebuilt on next access."""
    if hasattr(env.registry, '_muk_mcp_method_cache'):
        del env.registry._muk_mcp_method_cache
    if hasattr(env.registry, '_muk_mcp_method_cache_key'):
        del env.registry._muk_mcp_method_cache_key
