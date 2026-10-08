from __future__ import annotations

import time
from collections.abc import Callable
from contextlib import suppress

from odoo import models

from odoo.addons.muk_ai.tests.common import (
    AITestCommon,
    text_payload,
    tool_payload,
)
from odoo.addons.muk_ai.tools.runtime import TurnSuperseded

STREAMED = ('text_delta', 'reasoning_delta', 'tool_call_start', 'tool_call_args_delta')


class TestStreaming(AITestCommon):
    """Verify streamed deltas reach the chat live and a stop settles the answer."""

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    def _replay(self, deltas: list[tuple[str, dict]], payload: dict) -> Callable:
        """Build a provider round that streams ``deltas`` and then answers."""

        def stream(request: dict) -> dict:
            """Hand every delta to the session, then return the round result."""
            for kind, data in deltas:
                request['on_delta'](kind, data)
            return payload

        return stream

    def _script(self, session: models.BaseModel, steps: tuple[str, ...]) -> Callable:
        """Build a provider round that streams text while the user acts in between."""

        def stream(request: dict) -> dict:
            """Stream a chunk, stop the chat, ask again or wait, step by step."""
            for index, step in enumerate(steps):
                if step == 'chunk':
                    request['on_delta']('text', {'delta': f'part {index} '})
                elif step == 'stop':
                    session.action_stop()
                elif step == 'ask':
                    session.send_message('new question')
                else:
                    time.sleep(0.31)
            return text_payload('never persisted')

        return stream

    def _streamed(self, sent: list) -> list[tuple[str, str]]:
        """Merge the streamed session events into runs of ``(type, text)``."""
        runs = []
        for _target, _type, message in sent:
            if message.get('type') not in STREAMED:
                continue
            text = message['payload'].get('delta') or message['payload']['name']
            if runs and runs[-1][0] == message['type']:
                runs[-1] = (message['type'], runs[-1][1] + text)
            else:
                runs.append((message['type'], text))
        return runs

    # ----------------------------------------------------------
    # Tests
    # ----------------------------------------------------------

    def test_text_and_reasoning_deltas_are_coalesced(self):
        chunks = [f'chunk{index:02d} ' for index in range(40)]
        answer = ''.join(chunks)
        for label, deltas, streamed, events in (
            (
                'text',
                [('text', {'delta': c}) for c in chunks],
                {'text_delta': answer},
                39,
            ),
            (
                'reasoning',
                [('reasoning', {'delta': 'weighing it'}), ('text', {'delta': answer})],
                {'reasoning_delta': 'weighing it', 'text_delta': answer},
                1,
            ),
        ):
            with self.subTest(label):
                session = self._session()
                with (
                    self._capture_bus() as sent,
                    self._mock_responses([self._replay(deltas, text_payload(answer))]),
                ):
                    session.start('stream it')
                self.assertEqual(dict(self._streamed(sent)), streamed)
                self.assertLessEqual(
                    len(
                        [
                            message
                            for _t, _k, message in sent
                            if message.get('type') == 'text_delta'
                        ]
                    ),
                    events,
                )
                self.assertEqual((session.state, session.last_text), ('done', answer))

    def test_tool_deltas_stream_the_tool_block_after_the_text(self):
        arguments = '{"model": "res.partner", "limit": 5}'
        deltas = [
            ('text', {'delta': 'looking that up'}),
            ('tool_start', {'call_id': 'c1', 'name': 'search_read'}),
            *[
                ('tool_args', {'call_id': 'c1', 'delta': arguments[index : index + 8]})
                for index in range(0, len(arguments), 8)
            ],
        ]
        session = self._session()
        with (
            self._capture_bus() as sent,
            self._patch_tool(),
            self._mock_responses(
                [
                    self._replay(deltas, tool_payload(('search_read', {}, 'c1'))),
                    text_payload('found'),
                ]
            ),
        ):
            session.start('find partners')
        self.assertEqual(
            self._streamed(sent),
            [
                ('text_delta', 'looking that up'),
                ('tool_call_start', 'search_read'),
                ('tool_call_args_delta', arguments),
            ],
        )
        self.assertEqual(
            {
                message['payload']['call_id']
                for _t, _k, message in sent
                if message.get('type') in ('tool_call_start', 'tool_call_args_delta')
            },
            {'c1'},
        )

    def test_a_stop_mid_stream_settles_the_partial_answer(self):
        for steps, state, texts, last, iterations in (
            (('stop', 'chunk'), 'stopped', [], False, 0),
            (('chunk', 'stop', 'wait', 'chunk'), 'stopped', ['part 0 '], 'part 0 ', 0),
            (
                ('chunk', 'stop', 'ask', 'wait', 'chunk'),
                'done',
                ['new answer'],
                'new answer',
                1,
            ),
        ):
            with self.subTest(steps=steps):
                session = self._session()
                with (
                    self._mock_responses(
                        [self._script(session, steps), text_payload('new answer')]
                    ),
                    suppress(TurnSuperseded),
                ):
                    session.start('old question')
                replies = [
                    block['text']
                    for item in session.conversation
                    if item.get('role') == 'assistant'
                    for block in item['content']
                ]
                self.assertEqual(session.state, state)
                self.assertEqual(replies, texts)
                self.assertEqual(
                    [event['content'] for event in self._events(session, 'text')], texts
                )
                self.assertEqual(
                    (session.last_text, session.iteration_count), (last, iterations)
                )
