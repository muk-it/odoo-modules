import json


TERMINATING_TOOLS = frozenset({
    'open_record', 'open_view', 'open_action', 'show_notification',
})

TOOL_LOAD_TOOL = {
    'name': 'tool_load',
    'description': (
        "Fetch full schemas for tool names listed in the system prompt's "
        "<available_tools> block. Returns "
        "{loaded: {name: {description, inputSchema}}, unknown: [name, ...]} "
        "and, when `call` is provided, the inline result of executing "
        "one of the loaded tools in the same round-trip — use this "
        "ALWAYS for the common load-then-use pattern (skips an extra "
        "agent loop iteration). Once a name is loaded its schema "
        "stays in the tools array for the rest of the session — never "
        "reload it."
    ),
    'inputSchema': {
        'type': 'object',
        'properties': {
            'names': {
                'type': 'array',
                'items': {'type': 'string'},
                'minItems': 1,
                'description': (
                    "One or more tool names from the <available_tools> "
                    "list. Load multiple at once when you may need any "
                    "of them — saves round-trips."
                ),
            },
            'call': {
                'type': 'object',
                'description': (
                    "Optional: also execute one of the just-loaded "
                    "tools in this same response. The model receives "
                    "the schema AND the tool's result back in one "
                    "function_call_output, no follow-up turn needed. "
                    "Strongly preferred for one-shot lookups."
                ),
                'properties': {
                    'name': {
                        'type': 'string',
                        'description': (
                            "Tool name to execute. MUST be one of the "
                            "names being loaded in this call."
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
        "Pause the agent to ask the human a clarifying question. Use this "
        "when the request is ambiguous, when you need a concrete value the "
        "user has not provided, or when you need a yes/no confirmation "
        "before continuing. The session pauses in waiting state; the next "
        "session turn will contain the user's answer. Never call ask_user "
        "after calling other tools in the same round — ask before acting, "
        "not after.\n\n"
        "When you are about to perform an action you yourself judge as "
        "destructive, irreversible, or wide-impact (bulk update, mass "
        "delete, calling a state-changing method on financial records, "
        "sending external messages, etc.) — even on a model the system "
        "has not flagged as sensitive — ALWAYS pre-confirm by calling "
        "ask_user with `resolution='yesno'` and a structured `preview`. "
        "The UI then renders the rich diff card with Approve / Reject "
        "buttons instead of a plain text question."
    ),
    'inputSchema': {
        'type': 'object',
        'properties': {
            'question': {
                'type': 'string',
                'description': "A single clear question the user can answer in plain text.",
            },
            'options': {
                'type': 'array',
                'items': {'type': 'string'},
                'description': (
                    "Optional predefined answers. The UI renders each as a "
                    "clickable button that submits the option text as the "
                    "answer. Keep them short (a few words). Use this when "
                    "the answer is one of a small enumerable set."
                ),
            },
            'resolution': {
                'type': 'string',
                'enum': ['text', 'yesno'],
                'description': (
                    "How the user will resolve the question. 'text' "
                    "(default) accepts a free-text answer; 'yesno' shows "
                    "Approve / Allow-for-session / Reject buttons — use "
                    "when you need explicit confirmation before a "
                    "destructive or irreversible action."
                ),
            },
            'preview': {
                'type': 'object',
                'description': (
                    "Optional structured preview of what will happen if "
                    "the user confirms. The UI renders it as a rich card "
                    "with a field-by-field diff or list of targets. "
                    "Strongly recommended when resolution='yesno'. "
                    "Shape: {'kind': 'update'|'delete'|'create'|'call', "
                    "'model': 'res.model', 'model_label': 'Display Name', "
                    "'title': 'Update 3 Sales Order(s)', "
                    "'targets': [{'id': 1, 'display_name': 'SO/001'}, …], "
                    "'changes': [{'field': 'state', 'label': 'Status', "
                    "'from': 'Draft', 'to': 'Confirmed'}, …]  // for update; "
                    "'properties': [{'field': '…', 'label': '…', 'value': '…'}, …]  // for create; "
                    "'method': 'action_post'  // for call}."
                ),
            },
        },
        'required': ['question'],
    },
}


def build_tool_call_output(call_id, output):
    serialized = output if isinstance(output, str) else json.dumps(output, default=str)
    return {
        'type': 'function_call_output',
        'call_id': call_id,
        'output': serialized,
    }
