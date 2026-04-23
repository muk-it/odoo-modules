import json


TERMINATING_TOOLS = frozenset({
    'open_record', 'open_view', 'open_action', 'show_notification',
})

ASK_USER_TOOL = {
    'name': 'ask_user',
    'description': (
        "Pause the agent to ask the human a clarifying question. Use this "
        "when the request is ambiguous, when you need a concrete value the "
        "user has not provided, or when you need a yes/no confirmation "
        "before continuing. The session pauses in waiting state; the next "
        "session turn will contain the user's answer. Never call ask_user "
        "after calling other tools in the same round — ask before acting, "
        "not after."
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
                'description': "Optional predefined options. UI may render them as buttons.",
            },
            'resolution': {
                'type': 'string',
                'enum': ['text', 'yesno'],
                'description': (
                    "How the user will resolve the question. 'text' "
                    "(default) accepts a free-text answer; 'yesno' shows "
                    "approve/reject buttons — use when you need explicit "
                    "confirmation before an action."
                ),
            },
            'preview': {
                'type': 'object',
                'description': (
                    "Optional structured preview of what will happen if "
                    "the user confirms. The UI renders it as a rich card."
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
