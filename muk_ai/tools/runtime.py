from __future__ import annotations

import contextlib

import psycopg2

from odoo import models, modules
from odoo.api import Environment
from odoo.fields import Domain
from odoo.sql_db import PG_CONCURRENCY_EXCEPTIONS_TO_RETRY, Cursor
from odoo.tools import SQL


def commit_safe(env: Environment) -> None:
    """Commit outside tests, re-raising on serialization conflicts.

    A long job lands what it already paid for before the worker time limit;
    a test transaction is never committed.
    """
    if not modules.module.current_test:
        try:
            env.cr.commit()
        except PG_CONCURRENCY_EXCEPTIONS_TO_RETRY:
            env.cr.rollback()
            env.invalidate_all()
            raise


DEFAULT_CONTEXT_WINDOW = 128000

REASONING_EFFORT_SELECTION = [
    ('minimal', 'Minimal'),
    ('low', 'Low'),
    ('medium', 'Medium'),
    ('high', 'High'),
    ('xhigh', 'Extra High'),
    ('max', 'Maximum'),
]

REASONING_EFFORT_ORDER = tuple(key for key, _label in REASONING_EFFORT_SELECTION)


def nearest_reasoning_effort(effort: str, supported: list) -> str:
    """Return the supported tier closest to ``effort``, rounding down on ties."""
    candidates = [tier for tier in REASONING_EFFORT_ORDER if tier in supported]
    if not candidates or effort in candidates or effort not in REASONING_EFFORT_ORDER:
        return effort
    index = REASONING_EFFORT_ORDER.index(effort)
    return min(
        candidates,
        key=lambda tier: (
            abs(REASONING_EFFORT_ORDER.index(tier) - index),
            REASONING_EFFORT_ORDER.index(tier),
        ),
    )


MAX_ITERATIONS = 20
MAX_TOOL_CALLS_PER_ROUND = 10
ITERATION_WARNING_ROUNDS = 2
MAX_WALLCLOCK_SECONDS = 600
TURN_WALLCLOCK_SECONDS = 3600
CLIENT_ACTION_TIMEOUT_SECONDS = 600
WALLCLOCK_SAFETY_MARGIN = 30
WALLCLOCK_MIN_SECONDS = 30

GC_SESSION_BATCH = 1000

ADVISORY_LOCK_NAMESPACE = 0x4D554B41
WORKER_HEARTBEAT_INTERVAL = 5
WORKER_STALE_THRESHOLD = 60

DISPATCH_MAX_TURNS = 3

COMPACT_AUTO_RATIO = 0.80
COMPACT_SUMMARY_SYSTEM = (
    'You are performing a CONTEXT CHECKPOINT COMPACTION. '
    'Do NOT continue the conversation. Do NOT respond to any questions in it. '
    'Output ONLY the structured summary, in the same language as the conversation. '
    'These instructions and the closing request are not part of the conversation: '
    'never record them as a user request, a constraint or work in progress.\n\n'
    'Produce a handoff summary using exactly this Markdown structure. '
    'Keep section order. Preserve exact file paths, function names, error '
    'messages, and user-stated constraints.\n\n'
    '## Goal\n'
    '## Constraints & Preferences\n'
    '## Progress\n'
    '### Done\n'
    '### In Progress\n'
    '### Blocked\n'
    '## Key Decisions\n'
    '## Next Steps\n'
    '## Critical Context\n'
    '## Relevant Files\n'
)
COMPACT_SUMMARY_REINJECTION = (
    'Another language model produced this summary of earlier work. '
    'Use it to continue the task without duplicating completed work.'
)


def try_advisory_lock(cr: Cursor, key: int, xact: bool = False) -> bool:
    """Try to take the advisory lock of a session or of a dispatch slot.

    :param xact: hold the lock until the transaction ends, not until released
    """
    function = SQL('pg_try_advisory_xact_lock' if xact else 'pg_try_advisory_lock')
    cr.execute(SQL('SELECT %s(%s, %s)', function, ADVISORY_LOCK_NAMESPACE, key))
    return cr.fetchone()[0]


def advisory_unlock(cr: Cursor, key: int) -> None:
    """Release an advisory lock, rolling a failed transaction back first."""
    query = SQL('SELECT pg_advisory_unlock(%s, %s)', ADVISORY_LOCK_NAMESPACE, key)
    try:
        cr.execute(query)
    except psycopg2.Error:
        cr.rollback()
        with contextlib.suppress(psycopg2.Error):
            cr.execute(query)


def vacuum(model: models.BaseModel, domain: Domain, batch: int) -> tuple[int, int]:
    """Delete one batch of the records matching ``domain``.

    :return: how many were deleted, and how many are still due
    """
    stale = model.search(domain, limit=batch)
    count = len(stale)
    stale.unlink()
    return count, model.search_count(domain) if count >= batch else 0


class StreamCancelled(Exception):
    """Raised to abort an in-progress streaming agent turn."""


class TurnSuperseded(StreamCancelled):
    """Raised when a newer turn has replaced the one being streamed."""


def coerce_ids(values) -> list[int]:
    """Coerce an iterable of values into a list of integer ids, dropping non-numeric ones."""
    ids = []
    for value in values or []:
        if isinstance(value, bool):
            continue
        if isinstance(value, int):
            ids.append(value)
            continue
        if isinstance(value, str):
            try:
                ids.append(int(value))
            except ValueError:
                continue
    return ids


def sanitize_json_schema(schema) -> object:
    """Recursively normalize a JSON schema, ensuring arrays declare ``items``."""
    if not isinstance(schema, dict):
        return schema
    cleaned = dict(schema)
    if cleaned.get('type') == 'array' and 'items' not in cleaned:
        cleaned['items'] = {}
    if isinstance(cleaned.get('items'), dict):
        cleaned['items'] = sanitize_json_schema(cleaned['items'])
    if isinstance(cleaned.get('properties'), dict):
        cleaned['properties'] = {
            name: sanitize_json_schema(value)
            for name, value in cleaned['properties'].items()
        }
    for key in ('anyOf', 'oneOf', 'allOf'):
        if isinstance(cleaned.get(key), list):
            cleaned[key] = [sanitize_json_schema(s) for s in cleaned[key]]
    return cleaned
