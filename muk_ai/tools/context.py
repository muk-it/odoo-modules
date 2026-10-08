from __future__ import annotations

import json

from odoo.exceptions import UserError
from odoo.tools.translate import LazyTranslate

_lt = LazyTranslate('muk_ai')

VIEW_KINDS = {
    'record': {'display_name': str, 'ee_init_context': [str]},
    'list': {'view_type': str, 'domain': list},
    'action': {'action_id': int},
    'pivot': {
        'pivot_measures': [str],
        'pivot_row_groupby': [str],
        'pivot_column_groupby': [str],
        'domain': list,
    },
    'graph': {
        'graph_mode': str,
        'graph_measure': str,
        'graph_groupbys': [str],
        'graph_order': str,
        'domain': list,
    },
}

SEGMENT_LABELS = {
    'action_id': 'id',
    'pivot_measures': 'measures',
    'pivot_row_groupby': 'rows',
    'pivot_column_groupby': 'cols',
    'graph_mode': 'mode',
    'graph_measure': 'measure',
    'graph_groupbys': 'groupbys',
    'graph_order': 'order',
    'domain': 'domain',
}

TYPE_NAMES = {
    str: _lt('a string'),
    list: _lt('a list'),
    int: _lt('an integer'),
}


def _segments(payload: dict) -> list[str]:
    """Return the text segments describing a view or record context."""
    kind = payload.get('kind')
    if kind not in VIEW_KINDS:
        return []
    model = payload.get('model') or ''
    if kind == 'record':
        res_id, name = payload.get('id'), payload.get('display_name')
        head = [f'{model}/{res_id}' if res_id else model]
        return [*head, f'"{name}"'] if name and str(name) != str(res_id) else head
    segments = [model, payload.get('view_type') or kind]
    for key, label in SEGMENT_LABELS.items():
        if not (value := payload.get(key)):
            continue
        if key == 'domain':
            value = json.dumps(value, separators=(',', ':'))
        elif isinstance(value, list):
            value = ','.join(value)
        segments.append(f'{label}={value}')
    return segments


def _with_tag(inputs: list, payload: dict | None, tag: str) -> list:
    """Append a volatile user message carrying the context in ``<tag>``."""
    if not (body := ' · '.join(filter(None, _segments(payload or {})))):
        return inputs
    message = {
        'role': 'user',
        'content': [{'type': 'input_text', 'text': f'<{tag}>{body}</{tag}>'}],
        '_cache_volatile': True,
    }
    return [*(inputs or []), message]


def with_ui_ctx(inputs: list, payload: dict | None) -> list:
    """Append the ``<ui_ctx>`` message describing the pinned view."""
    return _with_tag(inputs, payload, 'ui_ctx')


def with_record_ctx(inputs: list, payload: dict | None) -> list:
    """Append the ``<linked_record>`` message describing a linked record."""
    return _with_tag(inputs, payload, 'linked_record')


def clean_view_context_payload(kind, payload: dict) -> dict:
    """Validate and normalize a view-context payload for the given kind.

    :raise UserError: when the kind is unknown or a value has the wrong type
    """
    if not isinstance(kind, str) or kind not in VIEW_KINDS:
        raise UserError(_lt('Invalid view context payload (kind=%(kind)r).', kind=kind))
    cleaned = {'kind': kind}
    if kind == 'record':
        if not isinstance(res_id := payload.get('id'), int) or res_id <= 0:
            raise UserError(_lt('view_context.id must be a positive integer.'))
        cleaned['id'] = res_id
    for key, expected in {'model': str, **VIEW_KINDS[kind]}.items():
        if not (value := payload.get(key)):
            continue
        if isinstance(expected, list):
            valid = isinstance(value, list) and all(isinstance(v, str) for v in value)
        else:
            valid = isinstance(value, expected)
        if not valid:
            expected_name = (
                _lt('a list of strings')
                if isinstance(expected, list)
                else TYPE_NAMES[expected]
            )
            raise UserError(
                _lt(
                    'view_context.%(key)s must be %(type)s.',
                    key=key,
                    type=expected_name,
                )
            )
        cleaned[key] = value
    if kind in ('pivot', 'graph'):
        cleaned['view_type'] = kind
    elif kind == 'list':
        cleaned.setdefault('view_type', 'list')
    return cleaned
