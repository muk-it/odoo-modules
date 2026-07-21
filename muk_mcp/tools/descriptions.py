from __future__ import annotations

import json
import textwrap
from typing import Any

_DOMAIN_EXAMPLES = '\n'.join(
    '  ' + json.dumps(d, ensure_ascii=False)
    for d in [
        [['is_company', '=', True]],
        ['|', ['email', 'ilike', '@gmail'], ['email', 'ilike', '@outlook']],
        [['state', '=', 'sale'], ['date_order', '>=', '2024-01-01']],
    ]
)

_CONTEXT_EXAMPLES = (
    f'{json.dumps({"active_test": False})} (include archived), '
    f'{json.dumps({"lang": "de_DE"})} (change language), '
    f'{json.dumps({"allowed_company_ids": [1]})} (target a company)'
)


def model_field() -> dict[str, Any]:
    """Return the JSON schema for a technical model-name parameter."""
    return {
        'type': 'string',
        'description': "Technical model name (e.g. 'res.partner').",
    }


def context_field() -> dict[str, Any]:
    """Return the JSON schema for an optional Odoo context-overrides parameter."""
    return {
        'type': 'object',
        'description': f'Optional Odoo context overrides. Examples: {_CONTEXT_EXAMPLES}.',
    }


def domain_field(extra_note: str = '') -> dict[str, Any]:
    """Return the JSON schema for an Odoo domain parameter, with optional note appended."""
    description = textwrap.dedent(
        """\
        JSON-encoded Odoo domain array. A condition is [field, operator, value];
        conditions are AND-ed by default. Combine with prefix logic operators
        placed BEFORE their operands: '|' (OR), '&' (AND, implicit), '!' (NOT) —
        never two logic operators in a row. Operators: =, !=, >, >=, <, <=, =?,
        like, ilike, =like, =ilike, not like, not ilike, in, not in, child_of,
        parent_of, any, not any. `field` may traverse relations with dotted paths
        (e.g. 'partner_id.country_id.code'); every field/relation must exist —
        verify with describe_model, never guess singular vs plural (_id vs _ids).
        `value` is a literal (string, number, list, bool), never another field.
        Examples (passed as JSON string):
        {examples}
        Pass [] or omit for no filter.
        """,
    ).format(
        examples=_DOMAIN_EXAMPLES,
    )
    if extra_note:
        description += extra_note
    return {'type': 'string', 'description': description}


def fields_field(
    *,
    required_hint: bool = True,
    example: list[str] | None = None,
    extra_note: str = '',
) -> dict[str, Any]:
    """Return the JSON schema for a field-names parameter, tuned by the given hints."""
    parts = ['Field names to return.']
    if required_hint:
        parts.append('ALWAYS specify this to avoid returning all fields (slow).')
    if extra_note:
        parts.append(extra_note)
    parts.append(
        f'Example: {json.dumps(example or ["name", "email", "state"])}.',
    )
    return {
        'type': 'array',
        'items': {'type': 'string'},
        'description': ' '.join(parts),
    }


def ids_field(verb: str = 'read', *, extra_note: str = '') -> dict[str, Any]:
    """Return the JSON schema for a record-IDs parameter phrased with the given verb."""
    description = f'Record IDs to {verb}.'
    if extra_note:
        description += f' {extra_note}'
    return {
        'type': 'array',
        'items': {'type': 'integer'},
        'description': description,
    }
