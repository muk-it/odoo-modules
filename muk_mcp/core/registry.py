from __future__ import annotations

from collections.abc import Callable
from typing import Any

from odoo.api import Environment

MIXIN = 'muk_mcp.mixin'
CACHE = '_muk_mcp_method_cache'


def stamp(
    attribute: str, name: str | None, description: str | None, **values: Any
) -> Callable:
    """Return a decorator marking a mixin method, named and described after it."""

    def decorator(func: Callable) -> Callable:
        """Store the definition on the function and return it unchanged."""
        summary = (func.__doc__ or '').strip().split('\n')[0]
        setattr(
            func,
            attribute,
            {
                'name': name or func.__name__,
                'description': description or summary or func.__name__,
                **values,
            },
        )
        return func

    return decorator


def _scan(env: Environment, attribute: str) -> dict[str, dict[str, Any]]:
    """Collect the mixin methods marked with ``attribute``, keyed by name.

    :raise ValueError: when two methods declare the same name.
    """
    index, seen = {}, set()
    for klass in env.registry[MIXIN].mro():
        for method, func in vars(klass).items():
            if method in seen or not (definition := getattr(func, attribute, None)):
                continue
            seen.add(method)
            if (name := definition['name']) in index:
                raise ValueError(
                    f'Duplicate {attribute} name {name!r}: declared on {method} '
                    f'and {index[name]["method"]}'
                )
            index[name] = {'kind': 'method', 'model': MIXIN, 'method': method}
            index[name].update(definition)
    return index


def get_index(
    env: Environment,
    attribute: str,
    model: str,
    fields: list[str],
    entry: Callable[[dict[str, Any]], dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    """Return the marked mixin methods and the active ``model`` records by name.

    The method scan is cached per registry and module set; a record shadows a
    method of the same name. ``entry`` turns a record read with ``fields`` into
    its index entry.
    """
    count = len(env.registry._init_modules)
    caches = vars(env.registry).setdefault(CACHE, {})
    if (cached := caches.get(attribute)) is None or cached[0] != count:
        cached = caches[attribute] = (count, _scan(env, attribute))
    index = dict(cached[1])
    records = env[model].sudo().search_read([('active', '=', True)], ['name', *fields])
    for record in records:
        index[record['name']] = {'kind': 'db', 'id': record['id'], **entry(record)}
    return index


def invalidate_registry_cache(env: Environment) -> None:
    """Drop the cached method scans so they are rebuilt on next access."""
    vars(env.registry).pop(CACHE, None)
