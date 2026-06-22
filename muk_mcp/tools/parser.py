import ast
import json
import re


_PY_LITERAL_PATTERN = re.compile(r'\b(true|false|null)\b')
_PY_LITERAL_MAP = {'true': 'True', 'false': 'False', 'null': 'None'}


def normalize_ids(ids):
    if ids is None:
        return []
    if isinstance(ids, int):
        return [ids]
    return list(ids)


def parse_literal(value):
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        substituted = _PY_LITERAL_PATTERN.sub(
            lambda m: _PY_LITERAL_MAP[m.group(1)], value,
        )
        return ast.literal_eval(substituted)


def coerce_json_value(value, max_passes=3):
    for _ in range(max_passes):
        if not isinstance(value, str):
            return value
        try:
            value = parse_literal(value)
        except (TypeError, ValueError, SyntaxError, MemoryError):
            return value
    return value
