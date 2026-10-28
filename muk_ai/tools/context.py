from __future__ import annotations

import json

from odoo.api import Environment
from odoo.exceptions import UserError


def _format_ctx_tag(payload, tag_name: str, kinds: dict | None = None) -> str | None:
    """Render a context payload into a ``<tag_name>...</tag_name>`` string.

    :param kinds: the kinds an addon adds, with the type of each value
    """
    payload = payload or {}
    kind = payload.get('kind')
    if builder := _SEGMENT_BUILDERS.get(kind):
        segments = builder(payload)
    elif kind in (kinds or {}):
        segments = _typed_segments(payload, kinds[kind])
    else:
        return None
    body = ' · '.join(s for s in segments if s)
    return f'<{tag_name}>{body}</{tag_name}>' if body else None


def _render_ctx(payload, tag_name: str, kinds: dict | None = None) -> dict | None:
    """Wrap a rendered context tag into a user input message, if any.

    The message is marked ``_cache_volatile`` because it is re-appended at
    the conversation tail every round with the current UI or record context:
    cache-aware providers anchor their breakpoint before it and strip the
    marker before it reaches the wire.
    """
    if not (tag := _format_ctx_tag(payload, tag_name, kinds)):
        return None
    return {
        'role': 'user',
        'content': [{'type': 'input_text', 'text': tag}],
        '_cache_volatile': True,
    }


def _with_ctx(inputs, payload, tag_name: str, kinds: dict | None = None) -> list:
    """Append the rendered context message for ``payload`` to ``inputs``."""
    if not (item := _render_ctx(payload, tag_name, kinds)):
        return inputs
    return list(inputs or []) + [item]


def format_ui_ctx_tag(payload) -> str | None:
    """Render the ``ui_ctx`` tag for a view-context payload."""
    return _format_ctx_tag(payload, 'ui_ctx')


def render_ui_ctx(payload) -> dict | None:
    """Render the ``ui_ctx`` payload as a user input message."""
    return _render_ctx(payload, 'ui_ctx')


def with_ui_ctx(inputs, payload, kinds: dict | None = None) -> list:
    """Append the ``ui_ctx`` message for ``payload`` to ``inputs``."""
    return _with_ctx(inputs, payload, 'ui_ctx', kinds)


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


def _typed_segments(p, types: dict) -> list[str]:
    """Build the display segments for a payload of a kind an addon adds."""
    segments = [p.get('model') or '', p.get('kind')]
    for key in types:
        if value := p.get(key):
            segments.append(
                f'{key}={",".join(value) if isinstance(value, list) else value}'
            )
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


def clean_view_context_payload(
    env: Environment, kind, payload, kinds: dict | None = None
) -> dict:
    """Validate and normalize a view-context payload for the given kind.

    :param kinds: the kinds an addon adds, with the type of each value
    :raise UserError: when the kind is invalid or unsupported.
    """
    if not isinstance(kind, str) or not kind.isidentifier() or kind.startswith('_'):
        raise UserError(
            env._(
                'Invalid view context payload (kind=%(kind)r).',
                kind=kind,
            )
        )
    if cleaner := _CLEANERS.get(kind):
        return cleaner(env, payload)
    if kind in (kinds or {}):
        return _clean_typed(env, kind, payload, kinds[kind])
    raise UserError(
        env._(
            'Invalid view context payload (kind=%(kind)r).',
            kind=kind,
        )
    )


def _base_payload(env: Environment, payload, kind: str) -> dict:
    """Build the common cleaned payload (kind plus optional model).

    :raise UserError: when ``model`` is present but not a string.
    """
    cleaned = {'kind': kind}
    if model := payload.get('model'):
        if not isinstance(model, str):
            raise UserError(env._('view_context.model must be a string.'))
        cleaned['model'] = model
    return cleaned


def _payload_domain(env: Environment, payload) -> list | None:
    """Return the validated ``domain`` from a payload, or ``None``.

    :raise UserError: when ``domain`` is present but not a list.
    """
    domain = payload.get('domain')
    if domain is None:
        return None
    if not isinstance(domain, list):
        raise UserError(env._('view_context.domain must be a list.'))
    return domain


def _clean_record(env: Environment, payload) -> dict:
    """Validate and normalize a record view-context payload.

    :raise UserError: when id, display_name, or ee_init_context are malformed.
    """
    cleaned = _base_payload(env, payload, 'record')
    res_id = payload.get('id')
    if not isinstance(res_id, int) or res_id <= 0:
        raise UserError(env._('view_context.id must be a positive integer.'))
    cleaned['id'] = res_id
    if display_name := payload.get('display_name'):
        if not isinstance(display_name, str):
            raise UserError(env._('view_context.display_name must be a string.'))
        cleaned['display_name'] = display_name
    if ee_init_context := payload.get('ee_init_context'):
        if not isinstance(ee_init_context, list) or any(
            not isinstance(v, str) for v in ee_init_context
        ):
            raise UserError(
                env._(
                    'view_context.ee_init_context must be a list of strings.',
                )
            )
        cleaned['ee_init_context'] = ee_init_context
    return cleaned


def _clean_list(env: Environment, payload) -> dict:
    """Validate and normalize a list view-context payload."""
    cleaned = _base_payload(env, payload, 'list')
    cleaned['view_type'] = payload.get('view_type') or 'list'
    if domain := _payload_domain(env, payload):
        cleaned['domain'] = domain
    return cleaned


def _clean_action(env: Environment, payload) -> dict:
    """Validate and normalize an action view-context payload.

    :raise UserError: when ``action_id`` is present but not an integer.
    """
    cleaned = _base_payload(env, payload, 'action')
    if action_id := payload.get('action_id'):
        if not isinstance(action_id, int):
            raise UserError(env._('view_context.action_id must be an integer.'))
        cleaned['action_id'] = action_id
    return cleaned


def _clean_string_list(env: Environment, payload, key: str) -> list[str] | None:
    """Return a validated list-of-strings payload value, or ``None``.

    :raise UserError: when the value is present but not a list of strings.
    """
    value = payload.get(key)
    if value is None:
        return None
    if not isinstance(value, list) or any(not isinstance(v, str) for v in value):
        raise UserError(
            env._(
                'view_context.%s must be a list of strings.',
                key,
            )
        )
    return value


def _clean_pivot(env: Environment, payload) -> dict:
    """Validate and normalize a pivot view-context payload."""
    cleaned = _base_payload(env, payload, 'pivot')
    cleaned['view_type'] = 'pivot'
    for key in ('pivot_measures', 'pivot_row_groupby', 'pivot_column_groupby'):
        if (value := _clean_string_list(env, payload, key)) is not None:
            cleaned[key] = value
    if domain := _payload_domain(env, payload):
        cleaned['domain'] = domain
    return cleaned


def _clean_graph(env: Environment, payload) -> dict:
    """Validate and normalize a graph view-context payload.

    :raise UserError: when a graph attribute is present but malformed.
    """
    cleaned = _base_payload(env, payload, 'graph')
    cleaned['view_type'] = 'graph'
    for key in ('graph_mode', 'graph_measure', 'graph_order'):
        value = payload.get(key)
        if value is not None:
            if not isinstance(value, str):
                raise UserError(env._('view_context.%s must be a string.', key))
            cleaned[key] = value
    if (groupbys := _clean_string_list(env, payload, 'graph_groupbys')) is not None:
        cleaned['graph_groupbys'] = groupbys
    if domain := _payload_domain(env, payload):
        cleaned['domain'] = domain
    return cleaned


def _clean_typed(env: Environment, kind: str, payload, types: dict) -> dict:
    """Validate and normalize a payload of a kind an addon adds.

    :raise UserError: when a value does not have its type
    """
    cleaned = _base_payload(env, payload, kind)
    for key, expected in types.items():
        if not (value := payload.get(key)):
            continue
        if isinstance(expected, list):
            valid = isinstance(value, list) and all(isinstance(v, str) for v in value)
        else:
            valid = isinstance(value, expected)
        if not valid:
            raise UserError(
                env._(
                    'view_context.%(key)s must be %(type)s.',
                    key=key,
                    type=env._('a list of strings')
                    if isinstance(expected, list)
                    else {
                        str: env._('a string'),
                        list: env._('a list'),
                        int: env._('an integer'),
                    }[expected],
                )
            )
        cleaned[key] = value
    return cleaned


_CLEANERS = {
    'record': _clean_record,
    'list': _clean_list,
    'action': _clean_action,
    'pivot': _clean_pivot,
    'graph': _clean_graph,
}
