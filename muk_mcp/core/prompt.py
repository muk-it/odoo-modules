from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from odoo.api import Environment


def _build_method_index(env: Environment) -> dict[str, dict[str, Any]]:
    """Scan the ``muk_mcp.mixin`` MRO for ``@mcp_prompt`` methods, keyed by prompt name.

    :raise ValueError: when two methods declare the same prompt name.
    """
    index = {}
    Model = env.registry.get('muk_mcp.mixin')
    if Model is None:
        return index
    seen = set()
    for klass in Model.mro():
        for attr_name, attr in vars(klass).items():
            if attr_name.startswith('__') or attr_name in seen:
                continue
            prompt_def = getattr(attr, '__mcp_prompt__', None)
            if not prompt_def or not isinstance(prompt_def, dict):
                continue
            seen.add(attr_name)
            name = prompt_def['name']
            if name in index:
                prev = index[name]
                raise ValueError(
                    'Duplicate @mcp_prompt name %r: declared on %s and %s'
                    % (
                        name,
                        attr_name,
                        prev['method'],
                    ),
                )
            index[name] = {
                'kind': 'method',
                'method': attr_name,
                'title': prompt_def.get('title'),
                'description': prompt_def['description'],
                'arguments': list(prompt_def.get('arguments') or []),
            }
    return index


def _fetch_db_index(env: Environment) -> dict[str, dict[str, Any]]:
    """Load active ``muk_mcp.prompt`` records into a name-keyed index."""
    index = {}
    if env.registry.get('muk_mcp.prompt') is None:
        return index
    records = (
        env['muk_mcp.prompt']
        .sudo()
        .search_read(
            [('active', '=', True)],
            fields=['id', 'name', 'title', 'description', 'arguments'],
        )
    )
    for record in records:
        raw_arguments = record.get('arguments')
        arguments = json.loads(raw_arguments) if raw_arguments else []
        index[record['name']] = {
            'kind': 'db',
            'id': record['id'],
            'title': record.get('title') or None,
            'description': record['description'],
            'arguments': arguments,
        }
    return index


def mcp_prompt(
    name: str | None = None,
    title: str | None = None,
    description: str | None = None,
    arguments: list[dict[str, Any]] | None = None,
) -> Callable:
    """Mark a mixin method as an MCP prompt, defaulting metadata from the function."""

    def decorator(func: Callable) -> Callable:
        """Stamp the prompt metadata onto the function and return it unchanged."""
        func.__mcp_prompt__ = {
            'name': name or func.__name__,
            'title': title,
            'description': (
                description
                or (func.__doc__ or '').strip().split('\n')[0]
                or func.__name__
            ),
            'arguments': list(arguments or []),
        }
        return func

    return decorator


def get_prompt_index(env: Environment) -> dict[str, dict[str, Any]]:
    """Return the merged method and DB prompt index, caching the method scan per registry.

    :return: prompt definitions keyed by name, DB prompts overriding method prompts.
    """
    cache_key = len(getattr(env.registry, '_init_modules', None) or ())
    method_index = getattr(env.registry, '_muk_mcp_prompt_cache', None)
    cached_key = getattr(env.registry, '_muk_mcp_prompt_cache_key', None)
    stale = method_index is None or (cached_key is not None and cached_key != cache_key)
    if stale:
        method_index = _build_method_index(env)
        env.registry._muk_mcp_prompt_cache = method_index
        env.registry._muk_mcp_prompt_cache_key = cache_key
    db_index = _fetch_db_index(env)
    return {**method_index, **db_index} if db_index else dict(method_index)


def invalidate_prompt_cache(env: Environment) -> None:
    """Drop the cached method prompt index so it is rebuilt on next access."""
    if hasattr(env.registry, '_muk_mcp_prompt_cache'):
        del env.registry._muk_mcp_prompt_cache
    if hasattr(env.registry, '_muk_mcp_prompt_cache_key'):
        del env.registry._muk_mcp_prompt_cache_key
