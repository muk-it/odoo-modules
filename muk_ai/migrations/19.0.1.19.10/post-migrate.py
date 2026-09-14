from __future__ import annotations

from psycopg2.extras import Json

from odoo.sql_db import Cursor

LEGACY_THINKING_TYPE = 'muk_ai_thinking'

SELECT_SESSIONS = """
    SELECT id, conversation
      FROM muk_ai_session
     WHERE jsonb_typeof(conversation) = 'array'
       AND EXISTS (
               SELECT 1
                 FROM jsonb_array_elements(conversation) AS item
                      CROSS JOIN LATERAL jsonb_array_elements(
                          CASE
                              WHEN jsonb_typeof(item->'content') = 'array'
                              THEN item->'content'
                              ELSE '[]'::jsonb
                          END
                      ) AS block
                WHERE block->>'type' = %s
           )
"""

UPDATE_SESSION = """
    UPDATE muk_ai_session
       SET conversation = %s
     WHERE id = %s
"""


def _rewrite_item(item: dict) -> dict:
    """Return the conversation item with its thinking blocks moved or dropped.

    A block Anthropic signed moves into that provider's private state, where
    the adapter replays it and no other vendor can see it. An unsigned one —
    what the OpenAI-compatible adapter used to write — authenticates nothing
    and is dropped.
    """
    content = item['content']
    signed = [
        {
            'type': 'thinking',
            'thinking': block['thinking'],
            'signature': block['signature'],
        }
        for block in content
        if isinstance(block, dict)
        and block.get('type') == LEGACY_THINKING_TYPE
        and block.get('thinking')
        and block.get('signature')
    ]
    migrated = {
        **item,
        'content': [
            block
            for block in content
            if not (
                isinstance(block, dict) and block.get('type') == LEGACY_THINKING_TYPE
            )
        ],
    }
    if signed and item.get('role') == 'assistant':
        state = dict(migrated.get('provider_state') or {})
        state['anthropic'] = {'thinking': signed}
        migrated['provider_state'] = state
    return migrated


def _rewrite_conversation(conversation: list) -> list:
    """Return the conversation with every legacy thinking block rewritten."""
    return [
        _rewrite_item(item)
        if isinstance(item, dict) and isinstance(item.get('content'), list)
        else item
        for item in conversation
    ]


def migrate(cr: Cursor, version: str) -> None:
    """Move stored thinking blocks out of the canonical content they rode on.

    Up to this version a signed Claude thought was a canonical content block,
    so handing the same conversation to another vendor replayed it there, and
    the OpenAI-compatible adapter wrote the same block type with an empty
    signature that Anthropic then had to reject. The block type is gone; this
    files what Anthropic signed under its own provider state, so a chat paused
    mid tool call keeps the thinking its next round has to replay.
    """
    cr.execute(SELECT_SESSIONS, (LEGACY_THINKING_TYPE,))
    for session_id, conversation in cr.fetchall():
        cr.execute(
            UPDATE_SESSION,
            (Json(_rewrite_conversation(conversation)), session_id),
        )
