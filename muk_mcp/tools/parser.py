from __future__ import annotations

import ast
import json
import re
from collections.abc import Iterable
from typing import Any

_PY_LITERAL_PATTERN = re.compile(r'\b(true|false|null)\b')
_PY_LITERAL_MAP = {'true': 'True', 'false': 'False', 'null': 'None'}


def normalize_ids(ids: int | Iterable[int] | None) -> list[int]:
    """Normalize a scalar, iterable, or ``None`` of ids into a list of ints."""
    if ids is None:
        return []
    if isinstance(ids, int):
        return [ids]
    return list(ids)


def parse_literal(value: str) -> Any:
    """Parse a string as JSON, falling back to Python literal evaluation.

    :raise ValueError: if the value is neither valid JSON nor a Python literal.
    """
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        substituted = _PY_LITERAL_PATTERN.sub(
            lambda m: _PY_LITERAL_MAP[m.group(1)],
            value,
        )
        return ast.literal_eval(substituted)


def coerce_json_value(value: Any, max_passes: int = 3) -> Any:
    """Repeatedly parse a possibly multiply-encoded JSON string into a value.

    Returns the value unchanged once it is no longer a parseable string or the
    pass limit is reached.
    """
    for _ in range(max_passes):
        if not isinstance(value, str):
            return value
        try:
            value = parse_literal(value)
        except (TypeError, ValueError, SyntaxError, MemoryError):
            return value
    return value
