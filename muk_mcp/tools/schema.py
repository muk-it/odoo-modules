from __future__ import annotations

from typing import Any

STRICT_SCHEMA_ALLOWED_KEYS = frozenset(
    {
        'type',
        'format',
        'description',
        'nullable',
        'enum',
        'properties',
        'required',
        'items',
        'propertyOrdering',
        'minimum',
        'maximum',
        'minItems',
        'maxItems',
        'minLength',
        'maxLength',
        'pattern',
    },
)


def to_strict_schema(schema: Any) -> Any:
    """Recursively strip a schema to allowed keys and normalize its types.

    Non-dict inputs are returned unchanged; object schemas always gain a
    ``properties`` map.
    """
    if not isinstance(schema, dict):
        return schema
    cleaned = {}
    for key, value in schema.items():
        if key not in STRICT_SCHEMA_ALLOWED_KEYS:
            continue
        if key == 'type':
            cleaned[key] = _normalize_type(value)
        elif key == 'properties' and isinstance(value, dict):
            cleaned[key] = {pk: to_strict_schema(pv) for pk, pv in value.items()}
        elif key == 'items':
            cleaned[key] = to_strict_schema(value)
        else:
            cleaned[key] = value
    if cleaned.get('type') == 'object' and 'properties' not in cleaned:
        cleaned['properties'] = {}
    return cleaned


def _normalize_type(value: Any) -> str:
    """Collapse a type value to a single non-null type string, defaulting to ``string``."""
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        for entry in value:
            if isinstance(entry, str) and entry != 'null':
                return entry
    return 'string'
