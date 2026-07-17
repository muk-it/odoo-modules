from __future__ import annotations

import json

from odoo.exceptions import UserError
from odoo.tools.translate import LazyTranslate

_lt = LazyTranslate('muk_ai')


def _format_ctx_tag(payload, tag_name: str) -> str | None:
    """Render a context payload into a ``<tag_name>...</tag_name>`` string."""
    payload = payload or {}
    builder = _SEGMENT_BUILDERS.get(payload.get('kind'))
    if not builder:
        return None
    body = ' · '.join(s for s in builder(payload) if s)
    return f'<{tag_name}>{body}</{tag_name}>' if body else None


def _render_ctx(payload, tag_name: str) -> dict | None:
    """Wrap a rendered context tag into a user input message, if any.

    The message is marked ``_cache_volatile`` because it is re-appended at
    the conversation tail every round with the current UI or record context:
    cache-aware providers anchor their breakpoint before it and strip the
    marker before it reaches the wire.
    """
    if not (tag := _format_ctx_tag(payload, tag_name)):
        return None
    return {
        'role': 'user',
        'content': [{'type': 'input_text', 'text': tag}],
        '_cache_volatile': True,
    }


def _with_ctx(inputs, payload, tag_name: str) -> list:
    """Append the rendered context message for ``payload`` to ``inputs``."""
    if not (item := _render_ctx(payload, tag_name)):
        return inputs
    return list(inputs or []) + [item]


def format_ui_ctx_tag(payload) -> str | None:
    """Render the ``ui_ctx`` tag for a view-context payload."""
    return _format_ctx_tag(payload, 'ui_ctx')


def render_ui_ctx(payload) -> dict | None:
    """Render the ``ui_ctx`` payload as a user input message."""
    return _render_ctx(payload, 'ui_ctx')


def with_ui_ctx(inputs, payload) -> list:
    """Append the ``ui_ctx`` message for ``payload`` to ``inputs``."""
    return _with_ctx(inputs, payload, 'ui_ctx')


def format_record_ctx_tag(payload) -> str | None:
    """Render the ``linked_record`` tag for a record-context payload."""
    return _format_ctx_tag(payload, 'linked_record')


def with_record_ctx(inputs, payload) -> list:
    """Append the ``linked_record`` message for ``payload`` to ``inputs``."""
    return _with_ctx(inputs, payload, 'linked_record')


def _record_segments(p) -> list[str]:
    res_id = p.get('id')
    model = p.get('model') or ''
    display = p.get('display_name') or ''
    head = f'{model}/{res_id}' if res_id else model
    if display and str(display) != str(res_id):
        return [head, f'"{display}"']
    return [head]


def _list_segments(p) -> list[str]:
    """Build the display segments for a list view-context payload."""
    segments = [p.get('model') or '', p.get('view_type') or 'list']
    if domain := p.get('domain'):
        segments.append(f'domain={json.dumps(domain, separators=(",", ":"))}')
    return segments


def _action_segments(p) -> list[str]:
    """Build the display segments for an action view-context payload."""
    segments = ['action']
    if action_id := p.get('action_id'):
        segments.append(f'id={action_id}')
    if model := p.get('model'):
        segments.append(model)
    return segments


def _pivot_segments(p) -> list[str]:
    """Build the display segments for a pivot view-context payload."""
    segments = [p.get('model') or '', 'pivot']
    if measures := p.get('pivot_measures'):
        segments.append(f'measures={",".join(measures)}')
    if rows := p.get('pivot_row_groupby'):
        segments.append(f'rows={",".join(rows)}')
    if cols := p.get('pivot_column_groupby'):
        segments.append(f'cols={",".join(cols)}')
    if domain := p.get('domain'):
        segments.append(f'domain={json.dumps(domain, separators=(",", ":"))}')
    return segments


def _graph_segments(p) -> list[str]:
    """Build the display segments for a graph view-context payload."""
    segments = [p.get('model') or '', 'graph']
    if mode := p.get('graph_mode'):
        segments.append(f'mode={mode}')
    if measure := p.get('graph_measure'):
        segments.append(f'measure={measure}')
    if groupbys := p.get('graph_groupbys'):
        segments.append(f'groupbys={",".join(groupbys)}')
    if order := p.get('graph_order'):
        segments.append(f'order={order}')
    if domain := p.get('domain'):
        segments.append(f'domain={json.dumps(domain, separators=(",", ":"))}')
    return segments


_SEGMENT_BUILDERS = {
    'record': _record_segments,
    'list': _list_segments,
    'action': _action_segments,
    'pivot': _pivot_segments,
    'graph': _graph_segments,
}


# ----------------------------------------------------------
# View context cleaners
# ----------------------------------------------------------


def clean_view_context_payload(kind, payload) -> dict:
    """Validate and normalize a view-context payload for the given kind.

    :raise UserError: when the kind is invalid or unsupported.
    """
    if not isinstance(kind, str) or not kind.isidentifier() or kind.startswith('_'):
        raise UserError(
            _lt(
                'Invalid view context payload (kind=%(kind)r).',
                kind=kind,
            )
        )
    cleaner = _CLEANERS.get(kind)
    if not cleaner:
        raise UserError(
            _lt(
                'Invalid view context payload (kind=%(kind)r).',
                kind=kind,
            )
        )
    return cleaner(payload)


def _base_payload(payload, kind: str) -> dict:
    """Build the common cleaned payload (kind plus optional model).

    :raise UserError: when ``model`` is present but not a string.
    """
    cleaned = {'kind': kind}
    if model := payload.get('model'):
        if not isinstance(model, str):
            raise UserError(_lt('view_context.model must be a string.'))
        cleaned['model'] = model
    return cleaned


def _payload_domain(payload) -> list | None:
    """Return the validated ``domain`` from a payload, or ``None``.

    :raise UserError: when ``domain`` is present but not a list.
    """
    domain = payload.get('domain')
    if domain is None:
        return None
    if not isinstance(domain, list):
        raise UserError(_lt('view_context.domain must be a list.'))
    return domain


def _clean_record(payload) -> dict:
    """Validate and normalize a record view-context payload.

    :raise UserError: when id, display_name, or ee_init_context are malformed.
    """
    cleaned = _base_payload(payload, 'record')
    res_id = payload.get('id')
    if not isinstance(res_id, int) or res_id <= 0:
        raise UserError(_lt('view_context.id must be a positive integer.'))
    cleaned['id'] = res_id
    if display_name := payload.get('display_name'):
        if not isinstance(display_name, str):
            raise UserError(_lt('view_context.display_name must be a string.'))
        cleaned['display_name'] = display_name
    if ee_init_context := payload.get('ee_init_context'):
        if not isinstance(ee_init_context, list) or any(
            not isinstance(v, str) for v in ee_init_context
        ):
            raise UserError(
                _lt(
                    'view_context.ee_init_context must be a list of strings.',
                )
            )
        cleaned['ee_init_context'] = ee_init_context
    return cleaned


def _clean_list(payload) -> dict:
    """Validate and normalize a list view-context payload."""
    cleaned = _base_payload(payload, 'list')
    cleaned['view_type'] = payload.get('view_type') or 'list'
    if domain := _payload_domain(payload):
        cleaned['domain'] = domain
    return cleaned


def _clean_action(payload) -> dict:
    """Validate and normalize an action view-context payload.

    :raise UserError: when ``action_id`` is present but not an integer.
    """
    cleaned = _base_payload(payload, 'action')
    if action_id := payload.get('action_id'):
        if not isinstance(action_id, int):
            raise UserError(_lt('view_context.action_id must be an integer.'))
        cleaned['action_id'] = action_id
    return cleaned


def _clean_string_list(payload, key: str) -> list[str] | None:
    """Return a validated list-of-strings payload value, or ``None``.

    :raise UserError: when the value is present but not a list of strings.
    """
    value = payload.get(key)
    if value is None:
        return None
    if not isinstance(value, list) or any(not isinstance(v, str) for v in value):
        raise UserError(
            _lt(
                'view_context.%s must be a list of strings.',
                key,
            )
        )
    return value


def _clean_pivot(payload) -> dict:
    """Validate and normalize a pivot view-context payload."""
    cleaned = _base_payload(payload, 'pivot')
    cleaned['view_type'] = 'pivot'
    for key in ('pivot_measures', 'pivot_row_groupby', 'pivot_column_groupby'):
        if (value := _clean_string_list(payload, key)) is not None:
            cleaned[key] = value
    if domain := _payload_domain(payload):
        cleaned['domain'] = domain
    return cleaned


def _clean_graph(payload) -> dict:
    """Validate and normalize a graph view-context payload.

    :raise UserError: when a graph attribute is present but malformed.
    """
    cleaned = _base_payload(payload, 'graph')
    cleaned['view_type'] = 'graph'
    for key in ('graph_mode', 'graph_measure', 'graph_order'):
        value = payload.get(key)
        if value is not None:
            if not isinstance(value, str):
                raise UserError(_lt('view_context.%s must be a string.', key))
            cleaned[key] = value
    if (groupbys := _clean_string_list(payload, 'graph_groupbys')) is not None:
        cleaned['graph_groupbys'] = groupbys
    if domain := _payload_domain(payload):
        cleaned['domain'] = domain
    return cleaned


_CLEANERS = {
    'record': _clean_record,
    'list': _clean_list,
    'action': _clean_action,
    'pivot': _clean_pivot,
    'graph': _clean_graph,
}
