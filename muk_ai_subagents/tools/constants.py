from __future__ import annotations

import hashlib
import json

# ----------------------------------------------------------
# Defaults
# ----------------------------------------------------------

DELEGATE_TOOL = 'delegate'
MESSAGE_TOOL = 'subagent_message'
LEAD_TOOLS = frozenset(
    {DELEGATE_TOOL, MESSAGE_TOOL, 'subagent_status', 'subagent_stop'}
)

STATUS_MESSAGES = 6
STATUS_MAX_MESSAGES = 20
STATUS_TEXT_CHARS = 500

MAX_TASKS = 5
MAX_CHILDREN = 5

LOCK_ATTEMPTS = 3

CHILD_COLORS = (
    'blue',
    'green',
    'orange',
    'purple',
    'red',
    'cyan',
    'pink',
    'yellow',
)

REPORT_PREVIEW_CHARS = 2000
ACTIVITY_ARGS_MAX_CHARS = 2000

TERMINAL_STATES = frozenset({'done', 'error', 'stopped'})

STOP_REASONS = [
    ('done', 'Done'),
    ('budget', 'Budget Exhausted'),
    ('no_progress', 'No Progress'),
    ('max_iterations', 'Max Iterations'),
    ('stopped', 'Stopped'),
    ('error', 'Error'),
]


LOOP_WINDOW = 8
LOOP_NOTICE_REPEATS = 3
LOOP_HALT_REPEATS = 5

SUBAGENT_RULES = (
    '<subagent>\n'
    'You are a subagent running one focused task for a parent agent. The '
    'parent waits until you report and sees nothing but your final message. '
    'Work through the brief in your first message, then reply with a final '
    'message in the requested output shape: what you found or did, what you '
    'could not do, and nothing else. Do not greet and do not ask what to do '
    'next. Ask the user only when the task cannot proceed without them, as '
    'every question pauses the whole run, and never to confirm a write: the '
    'system asks for approval itself where one is needed. A message from the '
    'user during the task is direction from the person the work is for: '
    'follow it.\n'
    '</subagent>'
)

DELEGATION_INSTRUCTIONS = (
    'Hand a part of a request to one of your delegates whenever it can run on '
    'its own: independent parts of one request, a part that takes many '
    'look-ups, work the user need not wait for, and always when the user asks '
    'for subagents or gives one of them a part by name. Hand the part over '
    'whole, its writes included, as the user asked for it: its subagent asks '
    'for any approval or detail it needs, so never ask for one yourself. Let a '
    'subagent that stopped finish its part by messaging it, instead of doing '
    'it yourself. '
    'Keep the synthesis for yourself, and do what a single tool call answers '
    'yourself.'
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
    """Render a delegation brief as the first message of a subagent."""
    return '\n'.join(
        f'{label}: {brief[key]}' for key, label in BRIEF_LABELS if brief.get(key)
    )


def tool_fingerprint(name: str, arguments: dict | None, result) -> str:
    """Return a stable digest of a tool call and what it returned."""
    args = json.dumps(arguments or {}, sort_keys=True, default=str)
    text = result if isinstance(result, str) else json.dumps(result, default=str)
    return hashlib.sha256(f'{name}|{args}|{text}'.encode()).hexdigest()[:32]


def loop_notice(name: str) -> str:
    """Return the note telling the model that a call keeps returning the same."""
    return (
        f'<loop_notice>You have called {name} with the same arguments '
        f'{LOOP_NOTICE_REPEATS} times and received the same result each time. '
        'Repeating it will not change the result: use what you have, take a '
        'different approach, or report. The task is stopped if the call is '
        f'repeated {LOOP_HALT_REPEATS} times.</loop_notice>'
    )


def report_notice(report: dict) -> str:
    """Return the note that hands a subagent's report to its lead."""
    return (
        f'<subagent_report subagent="{report["subagent"]}" agent="{report["agent"]}" '
        f'state="{report["state"]}" stop_reason="{report["stop_reason"]}">\n'
        f'{report["report"] or report["error"]}\n</subagent_report>'
    )
