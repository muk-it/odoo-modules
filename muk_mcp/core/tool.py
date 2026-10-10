from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from odoo.api import Environment

from odoo.addons.muk_mcp.core.registry import get_index, stamp
from odoo.addons.muk_mcp.tools.schema import to_strict_schema


def mcp_tool(
    name: str | None = None,
    description: str | None = None,
    input_schema: dict[str, Any] | None = None,
    category: str = 'read',
    registry: str | None = None,
    meta: dict[str, Any] | None = None,
    visibility: list[str] | None = None,
) -> Callable:
    """Mark a mixin method as an MCP tool, named and described after the function."""
    meta = dict(meta or {})
    if visibility is not None:
        meta['ui'] = {**(meta.get('ui') or {}), 'visibility': list(visibility)}
    return stamp(
        '__mcp_tool__',
        name,
        description,
        input_schema=input_schema or {'type': 'object'},
        category=category,
        registry=registry,
        meta=meta,
    )


def get_tool_index(
    env: Environment, registry: str | None = None
) -> dict[str, dict[str, Any]]:
    """Return the tool definitions by name, with strict input schemas.

    :param registry: keeps only the tools with no registry or one whose
        comma-separated list contains it.
    """
    index = get_index(
        env,
        '__mcp_tool__',
        'muk_mcp.tool',
        ['description', 'input_schema', 'category', 'registry'],
        lambda record: {
            'description': record['description'],
            'input_schema': json.loads(record['input_schema'] or '{"type": "object"}'),
            'category': record['category'],
            'registry': record['registry'] or None,
            'meta': {},
        },
    )
    return {
        name: {**entry, 'input_schema': to_strict_schema(entry['input_schema'])}
        for name, entry in index.items()
        if registry is None
        or not entry['registry']
        or registry in (part.strip() for part in entry['registry'].split(','))
    }
