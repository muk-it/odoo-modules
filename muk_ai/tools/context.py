import json


def format_ui_ctx_tag(payload):
    payload = payload or {}
    builder = _SEGMENT_BUILDERS.get(
        payload.get('kind')
    )
    if not builder:
        return None
    body = ' · '.join(s for s in builder(payload) if s)
    return f'<ui_ctx>{body}</ui_ctx>' if body else None


def render_ui_ctx(payload):
    if not (tag := format_ui_ctx_tag(payload)):
        return None
    return {
        'role': 'user',
        'content': [{'type': 'input_text', 'text': tag}],
    }


def with_ui_ctx(inputs, payload):
    if not (item := render_ui_ctx(payload)):
        return inputs
    return list(inputs or []) + [item]


def _record_segments(p):
    res_id = p.get('id')
    model = p.get('model') or ''
    display = p.get('display_name') or ''
    head = f'{model}/{res_id}' if res_id else model
    if display and str(display) != str(res_id):
        return [head, f'"{display}"']
    return [head]


def _list_segments(p):
    segments = [
        p.get('model') or '', p.get('view_type') or 'list'
    ]
    if domain := p.get('domain'):
        segments.append(
            f'domain={json.dumps(domain, separators=(",", ":"))}'
        )
    return segments


def _action_segments(p):
    segments = ['action']
    if action_id := p.get('action_id'):
        segments.append(f'id={action_id}')
    if model := p.get('model'):
        segments.append(model)
    return segments


_SEGMENT_BUILDERS = {
    'record': _record_segments,
    'list': _list_segments,
    'action': _action_segments,
}
