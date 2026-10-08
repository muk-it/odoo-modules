from __future__ import annotations

import time

from odoo import fields, models

from odoo.addons.muk_ai.tools.conversation import (
    count_messages,
    estimate_tokens,
    split_for_compact,
)
from odoo.addons.muk_ai.tools.runtime import (
    COMPACT_AUTO_RATIO,
    COMPACT_SUMMARY_REINJECTION,
    COMPACT_SUMMARY_SYSTEM,
)
from odoo.addons.muk_ai.tools.stream import StreamBuffer

PROGRESS_SAVE_SECONDS = 0.5


class AISessionCompact(models.AbstractModel):
    """Compaction of a chat: its history summarized into a shorter one."""

    _name = 'muk_ai.session.compact'
    _description = 'AI Session Compaction'
    _explanation = (
        'The part of a chat that summarizes its older messages once the '
        'conversation nears the context window of the model.'
    )

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    def _split_for_compact(self) -> tuple[list, list]:
        """Split the conversation into the prefix to summarize and the tail to keep."""
        keep_budget = max(2000, min(20000, self._resolve_context_window() // 5))
        return split_for_compact(list(self.conversation or []), keep_budget)

    def _maybe_auto_compact(self) -> None:
        """Compact a running session once its request nears the context window.

        Sized from the larger of the last reported and the estimated input;
        skipped when the kept tail alone already fills the ratio.
        """
        if not (conversation := self.conversation):
            return
        window = self._resolve_context_window()
        size = max(self.last_input_tokens or 0, sum(map(estimate_tokens, conversation)))
        if size / window < COMPACT_AUTO_RATIO:
            return
        _prefix, tail = self._split_for_compact()
        if sum(map(estimate_tokens, tail)) / window >= COMPACT_AUTO_RATIO:
            return
        self._begin_compact_progress(auto=True)
        self._transition_state('compacting')
        self.with_context(muk_ai_skip_done_notification=True)._do_compact(resume=True)
        if self.state == 'done':
            self._transition_state('running')

    def _begin_compact_progress(self, auto: bool = False) -> models.BaseModel:
        """Append and return a streaming compaction-progress event."""
        return self._append_event(
            {
                'kind': 'compact_progress',
                'name': '/compact',
                'auto': auto,
                'state': 'streaming',
                'message_count': count_messages(self.conversation or []),
                'tokens_estimate': self.last_input_tokens or 0,
                'started_at': fields.Datetime.now().isoformat(),
                'streamed_text': '',
            }
        )

    def _compact_events(self, limit: int) -> models.BaseModel:
        """Return the latest compaction-progress events, newest first."""
        return (
            self.env['muk_ai.session.event']
            .sudo()
            .search(
                [('session_id', '=', self.id), ('kind', '=', 'compact_progress')],
                order='sequence desc',
                limit=limit,
            )
        )

    def _patch_compact_progress(self, event: models.BaseModel, patch: dict) -> None:
        """Merge a patch into a compaction-progress event and broadcast it."""
        event.payload = {**(event.payload or {}), **patch}
        self._publish_event('compact_update', {'event_id': event.id, 'patch': patch})

    def _build_compact_inputs(self, prefix: list) -> list:
        """Build the summarization request inputs for a compaction.

        The checkpoint instructions travel in the system message, so the summary
        never mistakes them for a user request; an earlier summary is updated.
        """
        budget = max(500, min(4000, self._resolve_context_window() // 200))
        prompt = f'{COMPACT_SUMMARY_SYSTEM}Output at most {budget} tokens.\n'
        prior = next(
            (
                event.payload.get('summary')
                for event in self._compact_events(5)
                if (event.payload or {}).get('state') == 'done'
            ),
            None,
        )
        if prior:
            prompt = (
                f'{prompt}\n<previous-summary>\n{prior}\n</previous-summary>\n\n'
                'Update the structure above: preserve still-true points, drop '
                'stale ones, merge new info.'
            )
        return [
            {'role': 'system', 'content': [{'type': 'input_text', 'text': prompt}]},
            *prefix,
            {
                'role': 'user',
                'content': [{'type': 'input_text', 'text': 'Write the checkpoint.'}],
            },
        ]

    def _finish_compact(
        self, event: models.BaseModel, conversation: list, patch: dict, resume: bool
    ) -> None:
        """Replace the conversation, close the progress event and settle the session.

        Messages queued meanwhile start the next turn unless a turn resumes.
        """
        original = {
            'original_messages': count_messages(self.conversation or []),
            'original_tokens': event.payload['tokens_estimate'],
        }
        self.write(
            {
                'conversation': conversation,
                'pending_ask': False,
                'error_message': False,
                'last_input_tokens': 0,
                'cleared_at': fields.Datetime.now(),
            }
        )
        self._patch_compact_progress(event, {'state': 'done', **original, **patch})
        self._transition_state('done')
        if not resume and self.pending_ids:
            self._drain_pending_message()
            self._run_to_completion()

    def _do_compact(self, resume: bool = False) -> None:
        """Summarize the conversation prefix into a compact replacement.

        A failing provider drops the prefix without a summary instead.
        """
        event = self._compact_events(1)
        if (event.payload or {}).get('state') != 'streaming':
            event = self._begin_compact_progress()
        prefix, tail = self._split_for_compact()
        if not prefix:
            message = self.env._('Nothing to compact - conversation too short.')
            self._patch_compact_progress(
                event, {'state': 'cancelled', 'message': message}
            )
            self._transition_state('done')
            return
        stream = StreamBuffer(self._publish_now)

        def on_delta(kind: str, data: dict) -> None:
            """Stream the summary into the compaction progress event."""
            if kind != 'text' or not (delta := data.get('delta')):
                return
            stream.text += delta
            stream.add('compact_delta', delta, event_id=event.id)
            if (now := time.monotonic()) - stream.checked >= PROGRESS_SAVE_SECONDS:
                stream.checked = now
                event.payload = {**(event.payload or {}), 'streamed_text': stream.text}
                self._commit_safe()

        try:
            payload = self._resolve_provider()._request_responses(
                inputs=self._build_compact_inputs(prefix),
                tools_schema=None,
                on_delta=on_delta,
                model=self._effective_model(),
            )
        except Exception as error:
            notice = self.env._(
                'Compaction failed (%(error)s) - dropped %(dropped)s oldest '
                'message(s) without summary as a fallback.',
                error=str(error) or 'unknown error',
                dropped=count_messages(prefix),
            )
            self._finish_compact(
                event,
                tail,
                {'summary': notice, 'streamed_text': notice, 'fallback': 'tail_drop'},
                resume,
            )
            return
        if (event.payload or {}).get('state') == 'cancelled':
            self._transition_state('done')
            return
        self._accrue_usage(payload.get('usage'))
        if not (summary := (payload.get('text') or stream.text).strip()):
            message = self.env._('Compaction skipped: provider returned no summary.')
            self._patch_compact_progress(
                event, {'state': 'cancelled', 'message': message}
            )
            self._transition_state('done')
            return
        reinjected = {
            'type': 'message',
            'role': 'assistant',
            'content': [
                {
                    'type': 'output_text',
                    'text': f'{COMPACT_SUMMARY_REINJECTION}\n\n{summary}',
                }
            ],
        }
        self._finish_compact(
            event,
            [reinjected, *tail],
            {'summary': summary, 'streamed_text': summary},
            resume,
        )
