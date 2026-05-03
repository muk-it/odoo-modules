import json
import textwrap


_DOMAIN_EXAMPLES = '\n'.join('  ' + json.dumps(d, ensure_ascii=False) for d in [
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


def model_field():
    return {
        'type': 'string',
        'description': "Technical model name (e.g. 'res.partner').",
    }


def context_field():
    return {
        'type': 'object',
        'description': f'Optional Odoo context overrides. Examples: {_CONTEXT_EXAMPLES}.',
    }


def domain_field(extra_note=''):
    description = textwrap.dedent(
        """\
        JSON-encoded Odoo domain array. Conditions are [field, operator, value];
        AND-ed by default; use '|' for OR. Operators: =, !=, >, >=, <, <=, like,
        ilike, in, not in, child_of, parent_of. Examples (passed as JSON string):
        {examples}
        Pass [] or omit for no filter.
        """
    ).format(
        examples=_DOMAIN_EXAMPLES
    )
    if extra_note:
        description += extra_note
    return {'type': 'string', 'description': description}


def fields_field(*, required_hint=True, example=None, extra_note=''):
    parts = ['Field names to return.']
    if required_hint:
        parts.append('ALWAYS specify this to avoid returning all fields (slow).')
    if extra_note:
        parts.append(extra_note)
    parts.append(
        f'Example: {json.dumps(example or ["name", "email", "state"])}.'
    )
    return {
        'type': 'array',
        'items': {'type': 'string'},
        'description': ' '.join(parts),
    }


def ids_field(verb='read', *, extra_note=''):
    description = f'Record IDs to {verb}.'
    if extra_note:
        description += f' {extra_note}'
    return {
        'type': 'array',
        'items': {'type': 'integer'},
        'description': description,
    }
