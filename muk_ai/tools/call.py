from __future__ import annotations

import json

# ----------------------------------------------------------
# Tool Round Behavior
# ----------------------------------------------------------

TOOL_SUMMARY_MAX_CHARS = 120

TERMINATING_TOOLS = frozenset(
    {
        'open_record',
        'open_view',
        'open_action',
        'show_notification',
    }
)

# ----------------------------------------------------------
# Builtin Tool Schemas
# ----------------------------------------------------------

TOOL_LOAD_TOOL = {
    'name': 'tool_load',
    'description': (
        "Fetch full schemas for tool names listed in the system prompt's "
        '<available_tools> block. ONLY for names in that block: a tool '
        'already in your tools array is callable directly and must never '
        'be passed to tool_load. Use exact names, with no namespace '
        'prefix. Returns '
        '{loaded: {name: {description, inputSchema}}, unknown: [name, ...]} '
        'and, when `call` is provided, the inline result of executing '
        'one of the loaded tools in the same round-trip — always prefer '
        'that one-round-trip shape when loading a tool you intend to '
        'call (it skips an extra agent loop iteration). Once a name is '
        'loaded its schema stays in the tools array for the rest of the '
        'session — never reload it.'
    ),
    'inputSchema': {
        'type': 'object',
        'properties': {
            'names': {
                'type': 'array',
                'items': {'type': 'string'},
                'minItems': 1,
                'description': (
                    'One or more tool names from the <available_tools> '
                    'list, exactly as written there. Load multiple at '
                    'once when you may need any of them — saves '
                    'round-trips.'
                ),
            },
            'call': {
                'type': 'object',
                'description': (
                    'Optional: also execute one of the just-loaded '
                    'tools in this same response. The model receives '
                    "the schema AND the tool's result back in one "
                    'function_call_output, no follow-up turn needed. '
                    'Strongly preferred for one-shot lookups.'
                ),
                'properties': {
                    'name': {
                        'type': 'string',
                        'description': (
                            'Tool name to execute. MUST be one of the '
                            'names being loaded in this call.'
                        ),
                    },
                    'arguments': {
                        'type': 'object',
                        'description': "Arguments for that tool's call.",
                    },
                },
                'required': ['name'],
            },
        },
        'required': ['names'],
    },
}


ASK_USER_TOOL = {
    'name': 'ask_user',
    'description': (
        'Pause the agent to ask the human a clarifying question. Use this '
        'when the request is ambiguous, when you need a concrete value the '
        'user has not provided, or when you need a yes/no confirmation '
        'before continuing. The session pauses in waiting state; the next '
        "session turn will contain the user's answer. Never call ask_user "
        'after calling other tools in the same round — ask before acting, '
        'not after.\n\n'
        'When you are about to perform an action you yourself judge as '
        'destructive, irreversible, or wide-impact (bulk update, mass '
        'delete, calling a state-changing method on financial records, '
        'sending external messages, etc.) — even on a model the system '
        'has not flagged as sensitive — ALWAYS pre-confirm by calling '
        "ask_user with `resolution='yesno'` and a structured `preview`. "
        'The UI then renders the rich diff card with Approve / Reject '
        'buttons instead of a plain text question.'
    ),
    'inputSchema': {
        'type': 'object',
        'properties': {
            'question': {
                'type': 'string',
                'description': 'A single clear question the user can answer in plain text.',
            },
            'options': {
                'type': 'array',
                'items': {'type': 'string'},
                'description': (
                    'Optional predefined answers. The UI renders each as a '
                    'clickable button that submits the option text as the '
                    'answer. Keep them short (a few words). Use this when '
                    'the answer is one of a small enumerable set.'
                ),
            },
            'resolution': {
                'type': 'string',
                'enum': ['text', 'yesno'],
                'description': (
                    'How the user will resolve the question. "text" '
                    '(default) accepts a free-text answer; "yesno" shows '
                    'Approve / Allow-for-session / Reject buttons — use '
                    'when you need explicit confirmation before a '
                    'destructive or irreversible action.'
                ),
            },
            'preview': {
                'type': 'object',
                'description': (
                    'Optional structured preview of what will happen if '
                    'the user confirms. The UI renders it as a rich card '
                    'with a field-by-field diff or list of targets. '
                    'Strongly recommended when resolution="yesno". '
                    'Shape: {"kind": "update"|"delete"|"create"|"call", '
                    '"model": "res.model", "model_label": "Display Name", '
                    '"title": "Update 3 Sales Order(s)", '
                    '"targets": [{"id": 1, "display_name": "SO/001"}, …], '
                    '"changes": [{"field": "state", "label": "Status", '
                    '"from": "Draft", "to": "Confirmed"}, …]  // for update; '
                    '"properties": [{"field": "…", "label": "…", "value": "…"}, …]  // for create; '
                    '"method": "action_post"  // for call}.'
                ),
            },
        },
        'required': ['question'],
    },
}


_PREVIEW_LIST_FIELDS = {
    'update': ('targets', 'changes'),
    'delete': ('targets',),
    'call': ('targets',),
    'create': ('properties',),
}


def clean_ask_preview(preview) -> dict | None:
    """Coerce a model-supplied ask_user preview into the renderable shape."""
    if not isinstance(preview, dict):
        return None
    kind = preview.get('kind')
    if kind not in _PREVIEW_LIST_FIELDS:
        return None
    cleaned = {
        key: value
        for key, value in preview.items()
        if isinstance(key, str) and isinstance(value, (str, int, float, bool))
    }
    for field in _PREVIEW_LIST_FIELDS[kind]:
        value = preview.get(field)
        cleaned[field] = (
            [item for item in value if isinstance(item, dict)]
            if isinstance(value, list)
            else []
        )
    return cleaned


def summarize_tool_description(description) -> str:
    """Return a one-line tool summary bounded to ``TOOL_SUMMARY_MAX_CHARS``.

    Prefers the first sentence, then hard-truncates on a word boundary: some
    descriptions run for paragraphs with no early full stop, and tools defined
    as ``muk_mcp.tool`` records carry user-authored text of any length.
    """
    text = ' '.join(str(description or '').split())
    stop = text.find('. ')
    if 0 < stop < TOOL_SUMMARY_MAX_CHARS:
        return text[: stop + 1]
    if len(text) > TOOL_SUMMARY_MAX_CHARS:
        return text[: TOOL_SUMMARY_MAX_CHARS - 1].rsplit(' ', 1)[0] + '…'
    return text


def format_tool_signature(name: str, schema) -> str:
    """Return ``name(arg, required_arg*)`` for a tool's input schema.

    The deferred-tool list is the only thing a model sees before composing a
    one-round-trip ``tool_load`` call, so it has to carry the argument names:
    without them the arguments of that first call are guesswork. A schema
    stored on a ``muk_mcp.tool`` record is user-authored and validated as JSON
    only, so its shape is checked here as ``sanitize_json_schema`` does.
    """
    properties = schema.get('properties') if isinstance(schema, dict) else None
    if not isinstance(properties, dict) or not properties:
        return name
    required = schema.get('required')
    required = set(required) if isinstance(required, list) else set()
    args = ', '.join(f'{arg}*' if arg in required else arg for arg in properties)
    return f'{name}({args})'


def build_tool_call_output(call_id: str, output) -> dict:
    """Build a ``function_call_output`` item, serializing non-string output as JSON."""
    serialized = output if isinstance(output, str) else json.dumps(output, default=str)
    return {
        'type': 'function_call_output',
        'call_id': call_id,
        'output': serialized,
    }
