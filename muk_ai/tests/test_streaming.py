from __future__ import annotations

import io
import json
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from unittest.mock import MagicMock, patch

import requests
import urllib3
from psycopg2.errors import InFailedSqlTransaction, SerializationFailure

from odoo import models
from odoo.exceptions import UserError
from odoo.tools import mute_logger

from odoo.addons.muk_ai.tests.common import AITestCommon
from odoo.addons.muk_ai.tools import StreamCancelled


class TestAiStreaming(AITestCommon):
    """Verify streamed deltas, cancellation, and the provider stream reader."""

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    def _expect_cancelled(self, session: models.BaseModel, buffer_state: dict) -> None:
        """Run ``_check_cancelled`` and swallow the expected cancellation.

        ``BaseCase.assertRaises`` wraps the block in a savepoint and rolls it
        back, which would discard the partial message the check persists, so
        the raise is caught by hand instead.
        """
        try:
            session._check_cancelled(buffer_state)
        except StreamCancelled:
            return
        self.fail('_check_cancelled did not raise StreamCancelled')

    @contextmanager
    def _capture_published(self) -> Iterator[list]:
        """Record every published session event while still publishing it."""
        published = []
        session_cls = type(self.env['muk_ai.session'])
        original = session_cls._publish_event

        def spy(session, event_type, payload):
            published.append((event_type, payload))
            return original(session, event_type, payload)

        with patch.object(session_cls, '_publish_event', spy):
            yield published

    @contextmanager
    def _patch_stream(
        self,
        deltas: list[tuple[str, dict]],
        payload: dict | None = None,
        hook: Callable | None = None,
    ) -> Iterator[list]:
        """Patch the provider to replay ``deltas`` through the delta callback.

        :param deltas: ``(kind, payload)`` pairs handed to ``on_delta``
        :param payload: provider result returned once every delta was replayed
        :param hook: called with the index of the delta about to be emitted
        :return: the deltas actually handed to the session before it ended
        """
        emitted = []

        def fake(
            self_arg,
            inputs,
            tools_schema=None,
            text_schema=None,
            on_delta=None,
            model=None,
            **kwargs,
        ):
            for index, (kind, data) in enumerate(deltas):
                if hook is not None:
                    hook(index)
                emitted.append((kind, data))
                on_delta(kind, data)
            return self._make_text_response() if payload is None else payload

        with patch.object(
            type(self.provider),
            '_request_responses',
            autospec=True,
            side_effect=fake,
        ):
            yield emitted

    def _joined_deltas(self, published: list, event_type: str) -> str:
        """Join the ``delta`` of every published event of the given type."""
        return ''.join(
            payload.get('delta') or ''
            for kind, payload in published
            if kind == event_type
        )

    def _assistant_messages(self, session: models.BaseModel) -> list[str]:
        """Return the text of every assistant message in the conversation."""
        texts = []
        for item in session.conversation or []:
            if not isinstance(item, dict) or item.get('role') != 'assistant':
                continue
            texts.extend(
                block['text']
                for block in item.get('content') or []
                if isinstance(block, dict) and block.get('text')
            )
        return texts

    def _persisted_texts(self, session: models.BaseModel) -> list[str]:
        """Return the content of every persisted ``text`` event of a session."""
        events = (
            self.env['muk_ai.session.event']
            .sudo()
            .search(
                [('session_id', '=', session.id), ('kind', '=', 'text')],
                order='sequence',
            )
        )
        return [(event.payload or {}).get('content') or '' for event in events]

    def _sse_response(self, lines: Iterator[str]) -> MagicMock:
        """Build a mocked streaming HTTP response yielding the given lines."""
        response = MagicMock()
        response.iter_lines.return_value = lines
        response.raise_for_status.return_value = None
        return response

    def _byte_sse_response(self, body: bytes) -> requests.Response:
        """Build a real streaming response over raw bytes, as requests would.

        The content type carries no ``charset``, which is what OpenRouter
        sends and what makes requests fall back to ISO-8859-1.
        """
        response = requests.Response()
        response.status_code = 200
        response.headers['Content-Type'] = 'text/event-stream'
        response.encoding = requests.utils.get_encoding_from_headers(response.headers)
        response.raw = urllib3.HTTPResponse(
            body=io.BytesIO(body),
            status=200,
            preload_content=False,
        )
        return response

    # ----------------------------------------------------------
    # Tests: streamed deltas
    # ----------------------------------------------------------

    def test_text_deltas_are_coalesced_into_the_published_answer(self):
        session = self.env['muk_ai.session'].create({'name': 'stream-text'})
        chunks = [f'chunk{index:02d} ' for index in range(40)]
        answer = ''.join(chunks)
        deltas = [('text', {'delta': chunk}) for chunk in chunks]
        with self._capture_published() as published:
            with self._patch_stream(deltas, payload=self._make_text_response(answer)):
                session.start('stream please')
        text_events = [payload for kind, payload in published if kind == 'text_delta']
        self.assertEqual(self._joined_deltas(published, 'text_delta'), answer)
        self.assertLess(len(text_events), len(chunks))
        self.assertEqual(session.state, 'done')
        self.assertEqual(session.last_text, answer)

    def test_reasoning_deltas_stay_out_of_the_visible_answer(self):
        session = self.env['muk_ai.session'].create({'name': 'stream-reasoning'})
        thinking = 'weighing the hidden options before answering'
        answer = 'the visible answer'
        deltas = [
            ('reasoning', {'delta': thinking}),
            ('text', {'delta': answer}),
        ]
        with self._capture_published() as published:
            with self._patch_stream(deltas, payload=self._make_text_response(answer)):
                session.start('think first')
        self.assertEqual(self._joined_deltas(published, 'reasoning_delta'), thinking)
        self.assertEqual(self._joined_deltas(published, 'text_delta'), answer)
        self.assertEqual(session.last_text, answer)
        self.assertNotIn(thinking, json.dumps(session.conversation or []))
        self.assertNotIn(thinking, ''.join(self._persisted_texts(session)))

    def test_tool_deltas_stream_the_tool_block_after_the_text(self):
        session = self.env['muk_ai.session'].create({'name': 'stream-tools'})
        preface = 'looking that up'
        arguments = '{"model": "res.partner", "limit": 5}'
        parts = [arguments[index : index + 8] for index in range(0, len(arguments), 8)]
        deltas = [
            ('text', {'delta': preface}),
            ('tool_start', {'call_id': 'call_s1', 'name': 'search_records'}),
            *[('tool_args', {'call_id': 'call_s1', 'delta': part}) for part in parts],
        ]
        with self._capture_published() as published:
            with self._patch_stream(deltas):
                session._stream_provider_round(
                    self.provider,
                    [],
                    None,
                    self.env['muk_ai.agent'],
                )
        kinds = [kind for kind, _payload in published]
        self.assertIn('tool_call_start', kinds)
        start_index = kinds.index('tool_call_start')
        self.assertEqual(
            published[start_index][1],
            {'call_id': 'call_s1', 'name': 'search_records'},
        )
        self.assertEqual(
            self._joined_deltas(published[:start_index], 'text_delta'),
            preface,
        )
        args_events = [
            payload for kind, payload in published if kind == 'tool_call_args_delta'
        ]
        self.assertEqual(''.join(p['delta'] for p in args_events), arguments)
        self.assertEqual({p['call_id'] for p in args_events}, {'call_s1'})

    # ----------------------------------------------------------
    # Tests: cancellation
    # ----------------------------------------------------------

    def test_cancel_mid_stream_aborts_and_persists_the_partial_once(self):
        session = self.env['muk_ai.session'].create({'name': 'stream-cancel'})
        chunks = [f'part {index} ' for index in range(5)]
        deltas = [('text', {'delta': chunk}) for chunk in chunks]

        def stop_before_second(index):
            if index == 1:
                session.action_stop()
                time.sleep(0.31)

        with self._patch_stream(
            deltas,
            payload=self._make_text_response(''.join(chunks)),
            hook=stop_before_second,
        ) as emitted:
            session.start('stream then stop')
        self.assertEqual(len(emitted), 2)
        self.assertEqual(session.state, 'stopped')
        self.assertEqual(self._assistant_messages(session), [chunks[0]])
        self.assertEqual(self._persisted_texts(session), [chunks[0]])
        self.assertEqual(session.last_text, chunks[0])
        self.assertEqual(session.iteration_count, 0)
        self.assertEqual(session.total_output_tokens, 0)

    def test_second_cancel_does_not_duplicate_the_partial(self):
        session = self.env['muk_ai.session'].create({'name': 'stream-recancel'})
        session.write({'state': 'stopped'})
        buffer_state = {'full_text': 'half an answer'}
        self._expect_cancelled(session, buffer_state)
        buffer_state['last_state_check'] = 0
        self._expect_cancelled(session, buffer_state)
        self.assertEqual(buffer_state['full_text'], '')
        self.assertEqual(self._assistant_messages(session), ['half an answer'])
        self.assertEqual(self._persisted_texts(session), ['half an answer'])

    def test_cancel_with_empty_buffer_persists_no_assistant_message(self):
        session = self.env['muk_ai.session'].create({'name': 'stream-empty'})
        session.write({'state': 'stopped'})
        with self.assertRaises(StreamCancelled):
            session._check_cancelled({})
        self.assertEqual(self._assistant_messages(session), [])
        self.assertEqual(self._persisted_texts(session), [])
        self.assertFalse(session.last_text)

    # ----------------------------------------------------------
    # Tests: provider delta callback
    # ----------------------------------------------------------

    def test_call_on_delta_converts_transaction_failures_to_cancel(self):
        client = self.provider._get_client()
        for failure in (InFailedSqlTransaction, SerializationFailure):
            with self.subTest(failure=failure.__name__):

                def handler(kind, payload, failure=failure):
                    msg = 'transaction aborted'
                    raise failure(msg)

                with self.assertRaises(StreamCancelled):
                    client._call_on_delta(handler, 'text', {'delta': 'x'})

    @mute_logger('odoo.addons.muk_ai.providers.base')
    def test_call_on_delta_swallows_unrelated_handler_errors(self):
        client = self.provider._get_client()
        seen = []

        def handler(kind, payload):
            first = not seen
            seen.append(payload['delta'])
            if first:
                msg = 'handler exploded'
                raise ValueError(msg)

        client._call_on_delta(handler, 'text', {'delta': 'first'})
        client._call_on_delta(handler, 'text', {'delta': 'second'})
        self.assertEqual(seen, ['first', 'second'])

    # ----------------------------------------------------------
    # Tests: provider stream reader
    # ----------------------------------------------------------

    def test_post_stream_read_timeout_raises_stream_idle(self):
        client = self.provider._get_client()

        def timing_out():
            yield 'data: {"type": "ping"}'
            raise requests.exceptions.ReadTimeout

        response = self._sse_response(timing_out())
        with patch.object(requests.Session, 'post', return_value=response):
            with self.assertRaises(UserError) as caught:
                list(client._post_stream('/responses', {}))
        self.assertIn('Stream idle', str(caught.exception))

    def test_post_stream_skips_malformed_sse_lines(self):
        client = self.provider._get_client()
        response = self._sse_response(
            iter(
                [
                    '',
                    ': keep-alive comment',
                    'event: response.output_text.delta',
                    'data: ',
                    'data: [DONE]',
                    'data: {"broken": ',
                    'data: {"type": "ok", "index": 1}',
                ]
            )
        )
        with patch.object(requests.Session, 'post', return_value=response):
            payloads = list(client._post_stream('/responses', {}))
        self.assertEqual(payloads, [{'type': 'ok', 'index': 1}])

    def test_post_stream_decodes_utf8_without_a_charset_header(self):
        client = self.provider._get_client()
        text = 'überfällige Rechnungen „Grüße“'
        payload = json.dumps({'type': 'ok', 'text': text}, ensure_ascii=False)
        body = f'data: {payload}\n\n'
        response = self._byte_sse_response(body.encode())
        with patch.object(requests.Session, 'post', return_value=response):
            payloads = list(client._post_stream('/responses', {}))
        self.assertEqual(payloads, [{'type': 'ok', 'text': text}])
