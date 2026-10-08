from __future__ import annotations

import base64
import io
import json
import socket
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import patch

import requests
import urllib3

from odoo import fields, models, sql_db
from odoo.tests import TransactionCase
from odoo.tools import SQL

from odoo.addons.muk_ai.tools.runtime import ADVISORY_LOCK_NAMESPACE

HTML_PAGE = (
    b'<!doctype html><html><head><title>  Hello   World </title>'
    b'<style>.x{color:red}</style></head>'
    b'<body><nav>Home About</nav>'
    b'<main><h1>Heading</h1><p>First <a href="/docs">paragraph</a>.</p>'
    b'<script>var x = 1;</script>'
    b'<ul><li>one</li><li>two</li></ul>'
    b'<pre><code>code line</code></pre></main>'
    b'<footer>copyright</footer></body></html>'
)

PNG_BYTES = bytes.fromhex(
    '89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4'
    '890000000d49444154789c63f8cf00000003000100184b96c10000000049454e'
    '44ae426082'
)

PNG_1x1 = base64.b64encode(PNG_BYTES).decode()

USAGE = {'input_tokens': 10, 'output_tokens': 5}

PUBLIC_IP = '93.184.215.14'


def text_payload(text: str = 'ok', usage: dict | None = None) -> dict:
    """Build the provider result of a round that answers with plain text."""
    return {
        'text': text,
        'tool_calls': [],
        'carry_inputs': [
            {
                'type': 'message',
                'role': 'assistant',
                'content': [{'type': 'output_text', 'text': text}],
            }
        ],
        'usage': dict(USAGE if usage is None else usage),
    }


def tool_payload(*calls: tuple, usage: dict | None = None) -> dict:
    """Build the provider result of a round that calls tools.

    :param calls: ``(name, arguments)`` or ``(name, arguments, call_id)``;
        a missing call id is numbered ``call_1``, ``call_2``, ...
    """
    tool_calls = [
        {
            'call_id': call[2] if len(call) > 2 else f'call_{index}',
            'name': call[0],
            'arguments': call[1],
        }
        for index, call in enumerate(calls, 1)
    ]
    return {
        'text': '',
        'tool_calls': tool_calls,
        'carry_inputs': [
            {
                'type': 'function_call',
                'name': call['name'],
                'arguments': json.dumps(call['arguments']),
                'call_id': call['call_id'],
            }
            for call in tool_calls
        ],
        'usage': dict(USAGE if usage is None else usage),
    }


def json_response(payload, status_code: int = 200) -> requests.Response:
    """Build an HTTP response carrying ``payload`` as its JSON body."""
    response = requests.Response()
    response.status_code = status_code
    response._content = json.dumps(payload).encode()
    response.headers['Content-Type'] = 'application/json'
    response.url = 'https://provider.test/'
    return response


def sse_response(events: list, status_code: int = 200) -> requests.Response:
    """Build a streamed HTTP response sending each event as an SSE ``data:`` line.

    :param events: dicts are sent as JSON, strings as they are
    """
    lines = [
        f'data: {json.dumps(event) if isinstance(event, dict) else event}\n\n'
        for event in events
    ]
    response = requests.Response()
    response.status_code = status_code
    response.raw = io.BytesIO(''.join(lines).encode())
    response.headers['Content-Type'] = 'text/event-stream'
    response.url = 'https://provider.test/'
    return response


@contextmanager
def serve_web(pages: dict, dns: dict | None = None) -> Iterator[list[dict]]:
    """Serve ``pages`` at the DNS and connection pool boundary of a fetch.

    :param pages: URL mapped to ``(status, headers, body)``, any other 404s
    :param dns: host mapped to its addresses, ``None`` failing the lookup
    :return: every opened connection as ``{'ip', 'host', 'timeout', 'url'}``
    """
    dns = dns or {}
    connections = []

    def getaddrinfo(host, *args, **kwargs) -> list[tuple]:
        """Resolve ``host`` through the ``dns`` table."""
        if (ips := dns.get(host, (PUBLIC_IP,))) is None:
            raise socket.gaierror(host)
        return [(0, 0, 0, '', (ip, 0)) for ip in ips]

    def pool(**kwargs) -> SimpleNamespace:
        """Open a connection pool pinned to the address it was given."""
        connection = {
            'ip': kwargs['host'],
            'host': kwargs['assert_hostname'],
            'timeout': kwargs['timeout'],
        }
        connections.append(connection)

        def urlopen(method, path, headers, **options) -> SimpleNamespace:
            """Answer the request from ``pages``."""
            connection['url'] = f'https://{headers["Host"]}{path}'
            status, answer, body = pages.get(connection['url'], (404, {}, b''))
            chunks = body if isinstance(body, list) else [body]
            return SimpleNamespace(
                status=status,
                headers=answer,
                stream=lambda size: iter(chunks),
                release_conn=lambda: None,
            )

        return SimpleNamespace(urlopen=urlopen, close=lambda: None)

    with (
        patch.object(socket, 'getaddrinfo', side_effect=getaddrinfo),
        patch.object(urllib3, 'HTTPSConnectionPool', side_effect=pool),
    ):
        yield connections


class AITestCommon(TransactionCase):
    """Shared setup and boundary fakes for the AI provider and session tests.

    Cursors the code under test opens itself (a worker, the tool audit log)
    run inside the test transaction.
    """

    # ----------------------------------------------------------
    # Setup
    # ----------------------------------------------------------

    @classmethod
    def setUpClass(cls) -> None:
        """Give the three shipped providers a key and lift the chat rate limit."""
        super().setUpClass()
        cls.enterClassContext(cls.registry_test_mode())
        cls.provider = cls.env.ref('muk_ai.provider_openai')
        cls.provider_anthropic = cls.env.ref('muk_ai.provider_anthropic')
        cls.provider_google = cls.env.ref('muk_ai.provider_google')
        (cls.provider | cls.provider_anthropic | cls.provider_google).write(
            {'api_key': 'test-key', 'active': True, 'rate_limit': 0}
        )
        cls.env.company.default_ai_provider_id = cls.provider

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    def _session(self, **values) -> models.BaseModel:
        """Create a chat session owned by the current user."""
        return self.env['muk_ai.session'].create({'name': 'Test chat', **values})

    def _create_model(
        self,
        technical_name: str,
        modality: str = 'chat',
        provider: models.BaseModel | None = None,
        **values,
    ) -> models.BaseModel:
        """Create a catalogue model priced at one per million tokens."""
        return self.env['muk_ai.model'].create(
            {
                'name': technical_name,
                'provider_id': (provider or self.provider).id,
                'technical_name': technical_name,
                'modality': modality,
                'context_window': 400000 if modality == 'chat' else 0,
                'input_rate': 1.0,
                'output_rate': 1.0,
                **values,
            }
        )

    @classmethod
    def _clear_default_models(cls, modality: str = 'chat') -> None:
        """Unset the default model of the modality on every provider."""
        cls.env['muk_ai.provider'].with_context(active_test=False).search([]).write(
            {f'default_{modality}_model_id': False},
        )

    @classmethod
    def _mark_sensitive(cls, *model_names: str) -> None:
        """Flag the given models as sensitive, so every write on them asks first."""
        cls.env['ir.model'].sudo().search(
            [('model', 'in', list(model_names))],
        ).write({'ai_sensitive': True})

    def _set_params(self, values: dict) -> None:
        """Store config parameters with the typed setter matching each value."""
        params = self.env['ir.config_parameter'].sudo()
        for key, value in values.items():
            if isinstance(value, bool):
                params.set_bool(key, value)
            elif isinstance(value, int):
                params.set_int(key, value)
            elif isinstance(value, float):
                params.set_float(key, value)
            else:
                params.set_str(key, value)

    @contextmanager
    def _mock_responses(
        self, payloads: list[dict], repeat_last: bool = False
    ) -> Iterator[list[dict]]:
        """Answer each provider round with the next payload, in order.

        A payload may be a callable taking the request, or an exception to raise.
        Yields the keyword arguments of every request (``inputs``, ``on_delta``,
        ...), its attachments materialized as the provider sends them.
        """
        remaining = list(payloads)
        captured = []

        def fake(self_arg, inputs=None, **kwargs) -> dict:
            """Record the request and return the next scripted payload."""
            materialized = self_arg._materialize_inputs(inputs, kwargs.get('cache'))
            request = {**kwargs, 'inputs': materialized}
            captured.append(request)
            if not remaining:
                msg = 'No more mocked provider responses'
                raise AssertionError(msg)
            if repeat_last and len(remaining) == 1:
                answer = remaining[0]
            else:
                answer = remaining.pop(0)
            if isinstance(answer, Exception):
                raise answer
            return answer(request) if callable(answer) else answer

        with patch.object(
            type(self.env['muk_ai.provider']),
            '_request_responses',
            autospec=True,
            side_effect=fake,
        ):
            yield captured

    @contextmanager
    def _patch_tool(self, results: dict | None = None) -> Iterator[list[dict]]:
        """Serve every server-executed tool from ``results`` instead of running it.

        A result is a value, a callable taking the arguments, or an exception; a
        missing tool answers ``{"ok": true}``. Yields the calls made.
        """
        calls = []
        results = results or {}

        def fake(self_arg, name, arguments, env, enforce_scope) -> tuple:
            """Record the call and answer with the scripted result."""
            calls.append(
                {'name': name, 'arguments': arguments, 'context': dict(env.context)}
            )
            result = results.get(name, {'ok': True})
            if isinstance(result, Exception):
                raise result
            if callable(result):
                result = result(arguments)
            return self_arg._serialize_result(result), {}, arguments.get('model')

        with patch.object(
            type(self.env['muk_mcp.tool']), '_execute', autospec=True, side_effect=fake
        ):
            yield calls

    @contextmanager
    def _as_client_tool(self, *names: str, kind: str = 'webclient') -> Iterator[None]:
        """Register the given tools as executed by a client of ``kind``."""
        tool_cls = type(self.env['muk_mcp.tool'])
        original = tool_cls.get_tools

        def get_tools(self_arg, registry=None) -> list[dict]:
            """Return the real catalogue with the named tools run by the client."""
            meta = {'execute': 'client', 'client': kind}
            catalog = [
                {**entry, '_meta': meta} if entry.get('name') in names else entry
                for entry in original(self_arg, registry=registry)
            ]
            known = {entry.get('name') for entry in catalog}
            catalog += [
                {'name': name, 'description': name, 'inputSchema': {}, '_meta': meta}
                for name in names
                if name not in known
            ]
            return catalog

        with patch.object(tool_cls, 'get_tools', get_tools):
            yield

    @contextmanager
    def _capture_post(self, *responses) -> Iterator[list[tuple[str, dict]]]:
        """Answer each outgoing HTTP POST with the next response, in order.

        A response may be a ``requests.Response``, an exception to raise, or a
        callable taking the request keyword arguments and returning either.
        The yielded list collects every request as ``(url, kwargs)``.
        """
        remaining = list(responses)
        captured = []

        def fake(self_arg, url, **kwargs) -> requests.Response:
            """Record the request and return the next scripted response."""
            captured.append((url, kwargs))
            if not remaining:
                msg = f'No more mocked HTTP responses for {url}'
                raise AssertionError(msg)
            answer = remaining.pop(0)
            if callable(answer) and not isinstance(answer, requests.Response):
                answer = answer(kwargs)
            if isinstance(answer, Exception):
                raise answer
            return answer

        with patch.object(requests.Session, 'post', autospec=True, side_effect=fake):
            yield captured

    @contextmanager
    def _capture_bus(self) -> Iterator[list[tuple]]:
        """Collect every bus notification as ``(target, type, message)``."""
        captured = []

        def fake(self_arg, target, notification_type, message) -> None:
            """Record the notification instead of queueing it."""
            captured.append((target, notification_type, message))

        with patch.object(
            type(self.env['bus.bus']), '_sendone', autospec=True, side_effect=fake
        ):
            yield captured

    @contextmanager
    def _hold_lock(self, key: int) -> Iterator[None]:
        """Hold the advisory lock of a session or dispatch slot on another connection."""
        cursor = sql_db.db_connect(self.env.cr.dbname).cursor()
        try:
            cursor.execute(
                SQL(
                    'SELECT pg_try_advisory_lock(%s, %s)',
                    ADVISORY_LOCK_NAMESPACE,
                    key,
                )
            )
            if not cursor.fetchone()[0]:
                msg = f'lock {key} is already held'
                raise AssertionError(msg)
            yield
        finally:
            cursor.execute(
                SQL(
                    'SELECT pg_advisory_unlock(%s, %s)',
                    ADVISORY_LOCK_NAMESPACE,
                    key,
                )
            )
            cursor.close()

    def _backdate(
        self, records: models.BaseModel, delta: timedelta, *names: str
    ) -> None:
        """Move the given datetime columns of ``records`` ``delta`` into the past.

        :param names: columns to move, ``write_date`` when none is given
        """
        records.flush_recordset()
        when = fields.Datetime.now() - delta
        for name in names or ('write_date',):
            self.env.cr.execute(
                SQL(
                    'UPDATE %s SET %s = %s WHERE id IN %s',
                    SQL.identifier(records._table),
                    SQL.identifier(name),
                    when,
                    tuple(records.ids),
                )
            )
        records.invalidate_recordset()

    def _events(self, session: models.BaseModel, kind: str | None = None) -> list:
        """Return the session's transcript events, optionally of one kind."""
        events = session.fetch_events(limit=1000)['events']
        return [event for event in events if kind is None or event['kind'] == kind]

    def _outputs_for(self, session: models.BaseModel, call_id: str) -> list:
        """Return the tool outputs the conversation holds for ``call_id``."""
        return [
            item
            for item in session.conversation or []
            if isinstance(item, dict)
            and item.get('type') == 'function_call_output'
            and item.get('call_id') == call_id
        ]

    def _tool_output(self, session: models.BaseModel, call_id: str) -> dict:
        """Return the decoded tool output the conversation holds for ``call_id``."""
        return json.loads(self._outputs_for(session, call_id)[0]['output'])

    @staticmethod
    def _system_prompt(request: dict) -> str:
        """Return the system prompt a provider request carries."""
        return request['inputs'][0]['content'][0]['text']

    @staticmethod
    def _tools(request: dict) -> set[str]:
        """Return the names of the tools a provider request offers the model."""
        return {tool['name'] for tool in request['tools_schema'] or []}
