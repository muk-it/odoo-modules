from __future__ import annotations

from odoo.sql_db import Cursor


def migrate(cr: Cursor, version: str | None) -> None:
    """Turn scheduled chats into waiting ones and stop crons on cron expressions."""
    cr.execute(
        """
        ALTER TABLE muk_ai_session ADD COLUMN IF NOT EXISTS wake_at timestamp;
        UPDATE muk_ai_session
           SET state = 'waiting',
               wake_at = COALESCE(resume_at, now() AT TIME ZONE 'UTC'),
               pending_ask = jsonb_build_object(
                   'kind', 'wakeup',
                   'resume_at', to_char(
                       COALESCE(resume_at, now() AT TIME ZONE 'UTC'),
                       'YYYY-MM-DD HH24:MI:SS'
                   ),
                   'note', COALESCE(resume_prompt, recur_config->>'prompt', ''),
                   'record', false,
                   'condition', false,
                   'on_message', false
               )
         WHERE state = 'schedule';
        UPDATE ir_cron
           SET active = false
         WHERE id IN (
               SELECT cron_id
                 FROM muk_ai_schedule
                WHERE interval_type = 'cron'
          )
        """
    )
