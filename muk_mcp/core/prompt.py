from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from odoo.api import Environment

from odoo.addons.muk_mcp.core.registry import get_index, stamp


def mcp_prompt(
    name: str | None = None,
    title: str | None = None,
    description: str | None = None,
    arguments: list[dict[str, Any]] | None = None,
) -> Callable:
    """Mark a mixin method as an MCP prompt, named and described after the function."""
    return stamp(
        '__mcp_prompt__',
        name,
        description,
        title=title,
        arguments=list(arguments or []),
    )


def get_prompt_index(env: Environment) -> dict[str, dict[str, Any]]:
    """Return the prompt definitions by name."""
    return get_index(
        env,
        '__mcp_prompt__',
        'muk_mcp.prompt',
        ['title', 'description', 'arguments'],
        lambda record: {
            'title': record['title'],
            'description': record['description'],
            'arguments': json.loads(record['arguments'] or '[]'),
        },
    )
