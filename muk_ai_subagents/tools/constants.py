from __future__ import annotations

import hashlib
import json

# ----------------------------------------------------------
# Defaults Delegation
# ----------------------------------------------------------

DELEGATE_TOOL = 'delegate'

STEER_MAX_CHARS = 2000
STEER_MAX_QUEUED = 5

MAX_TASKS = 5
MAX_CHILDREN = 5

LOCK_ATTEMPTS = 3

CHILD_COLORS = (
    'red',
    'blue',
    'green',
    'yellow',
    'purple',
    'orange',
    'pink',
    'cyan',
)

SUMMARY_MAX_CHARS = 280

TERMINAL_STATES = frozenset({'done', 'error', 'stopped'})

STOP_REASONS = [
    ('done', 'Done'),
    ('budget', 'Budget Exhausted'),
    ('no_progress', 'No Progress'),
    ('max_iterations', 'Max Iterations'),
    ('stopped', 'Stopped'),
    ('error', 'Error'),
    ('stalled', 'Stalled'),
]

DELEGATION_SKIP_REASON = (
    'skipped: delegation pending, call again after the subagents have reported'
)

# ----------------------------------------------------------
# Defaults Limits
# ----------------------------------------------------------

DEFAULT_RUN_COST_LIMIT = 5.0
DEFAULT_STALL_SECONDS = 600

# ----------------------------------------------------------
# Defaults Loop
# ----------------------------------------------------------

LOOP_WINDOW = 8
LOOP_REPEATS = 3
LOOP_WITHHOLD_ROUNDS = 2

WITHHELD_SKIP_REASON = (
    'tool_withheld: this call keeps returning the same result; take a '
    'different approach or report what you have'
)

# ----------------------------------------------------------
# Defaults Prompts
# ----------------------------------------------------------

SUBAGENT_RULES = (
    '<subagent>\n'
    'You are a subagent agent running one focused task for a parent agent. '
    'The parent is paused until you report and sees nothing but your final '
    'message. Work through the brief in your first message, then reply with '
    'a final message in the requested output shape: what you found or did, '
    'what you could not do, and nothing else. Do not greet and do not ask '
    'what to do next. Ask the user only when the task cannot proceed '
    'without them, as every question pauses the whole run.\n'
    '</subagent>'
)

BRIEF_LABELS = (
    ('objective', 'Objective'),
    ('success_criteria', 'Success criteria'),
    ('output_shape', 'Output shape'),
    ('scope', 'Scope'),
    ('exclusions', 'Exclusions'),
)


# ----------------------------------------------------------
# Functions
# ----------------------------------------------------------


def render_brief(brief: dict) -> str:
    """Render a delegation brief as the first message of a child session."""
    lines = [f'{label}: {brief[key]}' for key, label in BRIEF_LABELS if brief.get(key)]
    return '\n'.join(lines)


def tool_fingerprint(name: str, arguments: dict | None, result) -> str:
    """Return a stable digest of a tool call and what it returned."""
    args = json.dumps(arguments or {}, sort_keys=True, default=str)
    text = result if isinstance(result, str) else json.dumps(result, default=str)
    return hashlib.sha256(f'{name}|{args}|{text}'.encode()).hexdigest()[:32]


def loop_notice(name: str, withheld: bool = False) -> dict:
    """Build the conversation entry telling the model it is repeating itself."""
    text = (
        f'You have called {name} with the same arguments {LOOP_REPEATS} times '
        'and received the same result each time. '
    )
    if withheld:
        text += (
            f'The tool is withheld for the next {LOOP_WITHHOLD_ROUNDS} rounds. '
            'Use what you already have or try a different approach.'
        )
    else:
        text += 'Repeating it again will not change the result; move on.'
    return {
        'role': 'user',
        'content': [
            {'type': 'input_text', 'text': f'<loop_notice>{text}</loop_notice>'}
        ],
    }
