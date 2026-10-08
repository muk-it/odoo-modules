from __future__ import annotations

import http.client
import io
import json
from collections.abc import Callable
from unittest.mock import patch

import requests
import urllib3
from psycopg2.errors import InFailedSqlTransaction, SerializationFailure

from odoo.exceptions import UserError

from odoo.addons.muk_ai.tests.common import sse_response
from odoo.addons.muk_ai.tests.providers import (
    CASES,
    USER,
    ProviderTestCase,
    deltas_of,
    openai_end,
    openai_event,
)
from odoo.addons.muk_ai.tools.http import http_session
from odoo.addons.muk_ai.tools.runtime import StreamCancelled

TEXT = 'Grüße über Fälligkeiten'

DELTA = json.dumps(openai_event('output_text.delta', delta=TEXT), ensure_ascii=False)

DONE = json.dumps(openai_end())


class _StalledBody(io.BytesIO):
    """Serve the buffered bytes, then time out like a socket whose peer went quiet."""

    def read(self, size: int | None = -1) -> bytes:
        """Return the buffered bytes, raising a socket timeout once they run out."""
        if chunk := super().read(size):
            return chunk
        raise TimeoutError


class TestHttp(ProviderTestCase):
    """Verify the pooled HTTP session, the SSE stream reader and the delta callback."""

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    def _raw(self, body: str, stalls: bool = False) -> requests.Response:
        """Build a streamed response the way requests builds it from raw bytes.

        The content type carries no charset, as OpenRouter sends it.
        """
        response = requests.Response()
        response.status_code = 200
        response.headers['Content-Type'] = 'text/event-stream'
        response.encoding = requests.utils.get_encoding_from_headers(response.headers)
        reader = (_StalledBody if stalls else io.BytesIO)(body.encode())
        response.raw = urllib3.HTTPResponse(body=reader, preload_content=False)
        return response

    def _failing(self, seen: list, failure: Exception) -> Callable[[str, dict], None]:
        """Return a delta handler recording each delta and failing on the first."""

        def handler(kind: str, data: dict) -> None:
            """Record the delta, raising ``failure`` on the first one."""
            seen.append(data['delta'])
            if len(seen) == 1:
                raise failure

        return handler

    # ----------------------------------------------------------
    # Tests
    # ----------------------------------------------------------

    def test_every_vendor_posts_through_one_pooled_session(self):
        sessions = []
        for name, case in CASES.items():
            with patch.object(
                requests.Session,
                'post',
                autospec=True,
                side_effect=lambda session, url, **kwargs: (
                    sessions.append(session) or sse_response(case.text)
                ),
            ):
                for _round in range(2):
                    self.providers[name]._request_responses(
                        inputs=[USER], on_delta=lambda kind, data: None
                    )
        self.assertEqual(len({id(session) for session in sessions}), 1)
        retry = sessions[0].get_adapter('https://api.openai.com').max_retries
        self.assertGreater(retry.connect, 0)
        self.assertEqual((retry.read, retry.status, retry.other), (False, 0, 0))

    def test_the_pooled_session_replays_only_a_dropped_connection(self):
        retry = http_session().get_adapter('https://api.openai.com').max_retries
        for reason in (
            ConnectionResetError(10054, 'reset by peer'),
            http.client.RemoteDisconnected('closed without response'),
            BrokenPipeError(32, 'broken pipe'),
        ):
            dropped = urllib3.exceptions.ProtocolError('Connection aborted.', reason)
            with self.subTest(reason=type(reason).__name__):
                self.assertEqual(
                    retry.increment('POST', '/v1/responses', error=dropped).connect,
                    retry.connect - 1,
                )
        for error in (
            urllib3.exceptions.ReadTimeoutError(None, '/v1/responses', 'timed out'),
            urllib3.exceptions.ProtocolError('Response ended prematurely'),
        ):
            with (
                self.subTest(error=type(error).__name__),
                self.assertRaises(type(error)),
            ):
                retry.increment('POST', '/v1/responses', error=error)

    def test_the_stream_reader_keeps_only_whole_data_events(self):
        for label, body in (
            ('utf-8 without a charset', f'data: {DELTA}\n\ndata: {DONE}\n\n'),
            (
                'noise between events',
                '\n'.join(
                    [
                        ': keep-alive',
                        'event: response.output_text.delta',
                        'data: ',
                        'data: [DONE]',
                        'data: {"broken": ',
                        f'data: {DELTA}',
                        '',
                        f'data: {DONE}',
                        '',
                    ]
                ),
            ),
        ):
            with self.subTest(stream=label):
                result, deltas, _sent = self._stream('openai', self._raw(body))
                self.assertEqual(
                    (result['text'], deltas_of(deltas, 'text')), (TEXT, [TEXT])
                )
        with (
            self.subTest(stream='stalled'),
            self._wire(self._raw(f'data: {DELTA}\n\n', stalls=True)),
            self.assertRaisesRegex(UserError, 'Stream idle for 45s'),
        ):
            self.providers['openai']._request_responses(
                inputs=[USER], on_delta=lambda kind, data: None
            )

    def test_a_failing_delta_handler_never_breaks_the_stream(self):
        for failure, cancels in (
            (ValueError('handler exploded'), False),
            (InFailedSqlTransaction('transaction aborted'), True),
            (SerializationFailure('concurrent update'), True),
        ):
            with self.subTest(failure=type(failure).__name__):
                seen = []
                handler = self._failing(seen, failure)
                if cancels:
                    with (
                        self._wire(CASES['openai'].text),
                        self.assertRaises(StreamCancelled),
                    ):
                        self.providers['openai']._request_responses(
                            inputs=[USER], on_delta=handler
                        )
                    self.assertEqual(seen, ['Hel'])
                    continue
                with (
                    self.assertLogs('odoo.addons.muk_ai.providers.base', 'ERROR'),
                    self._wire(CASES['openai'].text),
                ):
                    result = self.providers['openai']._request_responses(
                        inputs=[USER], on_delta=handler
                    )
                self.assertEqual((seen, result['text']), (['Hel', 'lo'], 'Hello'))
