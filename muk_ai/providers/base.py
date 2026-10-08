from __future__ import annotations

import json
import logging
from collections.abc import Callable, Iterator

import psycopg2
import requests
import urllib3

from odoo import models
from odoo.api import Environment
from odoo.exceptions import UserError

from odoo.addons.muk_ai.providers.region import Region
from odoo.addons.muk_ai.tools.http import http_session
from odoo.addons.muk_ai.tools.runtime import StreamCancelled

_logger = logging.getLogger(__name__)

PROVIDER_STATE_KEY = 'provider_state'


class ProviderBase:
    """Base class for AI provider adapters: config, HTTP, and streaming helpers."""

    name = ''
    label = ''
    default_model = ''
    default_url = ''
    regions: tuple[Region, ...] = ()

    supports_vision = True
    supports_web_search = False
    supports_code_interpreter = False

    reasoning_error_tokens = ()

    # ----------------------------------------------------------
    # Setup
    # ----------------------------------------------------------

    def __init__(self, provider: models.BaseModel) -> None:
        """Store the owning ``muk_ai.provider`` record supplying all config."""
        self.provider = provider

    # ----------------------------------------------------------
    # Properties
    # ----------------------------------------------------------

    @property
    def env(self) -> Environment:
        """Return the environment of the owning provider record."""
        return self.provider.env

    @classmethod
    def region(cls, code: str | None) -> Region | None:
        """Return the declared region with the given code, if any."""
        return next((region for region in cls.regions if region.code == code), None)

    @property
    def api_url(self) -> str:
        """Return the endpoint for the configured region, or the implementation default."""
        provider = self.provider.sudo()
        if provider.api_region == 'custom':
            return provider.api_url or ''
        region = self.region(provider.api_region)
        return (region.url if region else None) or self.default_url

    @property
    def _api_key(self) -> str:
        """Return the configured API key, empty when unset."""
        return self.provider.sudo().api_key or ''

    @property
    def authenticated(self) -> bool:
        """Return whether this account holds the credentials the vendor requires.

        An adapter whose endpoint may need none, a local Ollama behind the
        OpenAI-compatible wire, overrides this; :attr:`api_key` follows it.
        """
        return bool(self._api_key)

    @property
    def api_key(self) -> str:
        """Return the configured API key.

        :raise UserError: when no API key is configured.
        """
        if not self.authenticated:
            raise UserError(
                self.env._(
                    '%(provider)s API key is not configured.',
                    provider=self.label,
                )
            )
        return self._api_key

    def model_for(self, override: str | None = None) -> str:
        """Return the override, the record default model, or the class default."""
        return (
            override
            or self.provider._default_model('chat').technical_name
            or self.default_model
        )

    # ----------------------------------------------------------
    # Functions
    # ----------------------------------------------------------

    def headers(self) -> dict:
        """Return the HTTP headers for a provider request."""
        raise NotImplementedError

    def serves_builtin_tools(self, model: str) -> bool:
        """Return whether the model runs built-in tools next to function calling.

        A session always declares its Odoo tools, so a model that cannot
        combine the two serves no built-in capability at all.
        """
        return True

    def request(
        self,
        inputs: list[dict],
        tools_schema: list[dict] | None = None,
        text_schema: dict | None = None,
        on_delta: Callable | None = None,
        model: str | None = None,
        enable_web_search: bool = False,
        enable_code_interpreter: bool = False,
        cache_key: str | None = None,
        reasoning_effort: str | None = None,
    ) -> dict:
        """Stream an inference request and return its result.

        Deltas reach ``on_delta`` while the answer streams; without one the
        result is only assembled.
        """
        raise NotImplementedError

    def test_connection(self) -> bool:
        """Issue a minimal request to verify the provider responds.

        :raise UserError: when the provider returns an empty response.
        """
        payload = self.request(
            inputs=[
                {'role': 'system', 'content': 'Reply with a single word.'},
                {'role': 'user', 'content': 'Say: ok'},
            ],
        )
        if not payload.get('text'):
            raise UserError(
                self.env._(
                    'AI provider returned an empty response during the connection test.'
                )
            )
        return True

    def generate_image(
        self,
        model: str,
        prompt: str,
        options: dict | None = None,
    ) -> dict:
        """Render one image through the OpenAI ``/images/generations`` wire.

        :raise UserError: when the request fails or no image data comes back
        """
        body = {
            'model': model,
            'prompt': prompt,
            **{key: value for key, value in (options or {}).items() if value},
        }
        if not model.startswith('gpt-image'):
            body['response_format'] = 'b64_json'
        payload = self._post_json(
            '/images/generations', body, timeout=self.provider.image_timeout
        )
        entry = next(iter(payload.get('data') or []), None) or {}
        if not (data_b64 := entry.get('b64_json')):
            self._raise(self.env._('no image data returned'))
        return {
            'data_b64': data_b64,
            'mimetype': 'image/png',
            'revised_prompt': entry.get('revised_prompt') or '',
            'usage': {'images': 1},
        }

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    _http_session = staticmethod(http_session)

    def _post(
        self, path: str, body: dict, timeout: int, stream: bool = False
    ) -> requests.Response:
        """POST a JSON body to the endpoint and return the response.

        :raise UserError: on a transport error or an error status
        """
        try:
            response = self._http_session().post(
                f'{self.api_url}{path}',
                headers=self.headers(),
                json=body,
                timeout=timeout,
                stream=stream,
            )
            response.raise_for_status()
        except requests.HTTPError as error:
            self._raise(error.response.text or error)
        except requests.RequestException as error:
            self._raise(error)
        return response

    def _post_json(self, path: str, body: dict, timeout: int | None = None) -> dict:
        """POST a JSON body and return the decoded response.

        :param timeout: budget in seconds, the chat request timeout by default
        :raise UserError: on a transport error or an error status
        """
        return self._post(path, body, timeout or self.provider.request_timeout).json()

    def _post_stream(self, path: str, body: dict) -> Iterator[dict]:
        """POST a JSON body and yield the decoded SSE ``data:`` payloads.

        :raise UserError: on a transport error, an error status or an idle stream
        """
        timeout = self.provider.idle_timeout
        response = self._post(path, body, timeout, stream=True)
        response.encoding = 'utf-8'
        try:
            yield from self._sse_events(response)
        except requests.ConnectionError as error:
            if isinstance(error.__context__, urllib3.exceptions.ReadTimeoutError):
                self._raise(self.env._('Stream idle for %ss - aborted', timeout))
            self._raise(error)
        except requests.RequestException as error:
            self._raise(error)
        finally:
            response.close()

    @staticmethod
    def _sse_events(response: requests.Response) -> Iterator[dict]:
        """Yield the decoded ``data:`` payloads of a server-sent event stream."""
        for line in response.iter_lines(decode_unicode=True):
            data = line[5:].strip() if line.startswith('data:') else ''
            if not data or data == '[DONE]':
                continue
            try:
                event = json.loads(data)
            except ValueError:
                continue
            yield event

    def _invoke_with_reasoning_retry(
        self,
        model: str,
        invoke: Callable,
        on_delta: Callable | None,
        stages: tuple,
    ) -> dict:
        """Run ``invoke``, retrying without the reasoning config the provider rejected.

        An error naming :attr:`reasoning_error_tokens` pops each stage's keys in
        turn; no retry fires once deltas were streamed.
        """
        delivered = False

        def guarded(kind: str, data: dict) -> None:
            """Forward a delta and remember that one was delivered."""
            nonlocal delivered
            delivered = True
            on_delta(kind, data)

        callback = guarded if callable(on_delta) else on_delta
        try:
            return invoke(callback)
        except UserError as exc:
            message = str(exc).lower()
            if delivered or not any(
                token in message for token in self.reasoning_error_tokens
            ):
                raise
            error = exc
            for config, keys in stages:
                if not any(key in config for key in keys):
                    continue
                for key in keys:
                    config.pop(key, None)
                try:
                    result = invoke(callback)
                except UserError as retry_error:
                    if delivered:
                        raise
                    error = retry_error
                    continue
                _logger.warning(
                    'Model %s (%s) rejected its reasoning configuration (%s); '
                    'the request was served without it. Correct the model '
                    'catalog entry or the agent effort.',
                    model,
                    self.name,
                    ', '.join(keys),
                )
                return result
            raise error

    def _result(
        self,
        text: str,
        tool_calls: list,
        carry: list,
        usage: dict,
        on_delta: Callable | None = None,
        truncated: bool = False,
        limit: int | None = None,
    ) -> dict:
        """Assemble the result of a request, noting an answer cut at the token cap.

        :param limit: the output-token cap that was hit, when known
        """
        result = {
            'text': text.strip(),
            'tool_calls': tool_calls,
            'carry_inputs': carry,
            'usage': usage,
        }
        return self._apply_truncation(result, on_delta, limit) if truncated else result

    @classmethod
    def _tool_call(cls, call_id: str, name: str, arguments) -> dict:
        """Build a tool call of the result, decoding its JSON arguments."""
        parsed, error = cls._parse_tool_arguments(arguments)
        return {
            'call_id': call_id,
            'name': name,
            'arguments': parsed,
            '_parse_error': error,
        }

    @staticmethod
    def _call_item(call: dict) -> dict:
        """Return the ``function_call`` item carrying a tool call into the history."""
        return {
            'type': 'function_call',
            'name': call['name'],
            'arguments': json.dumps(call['arguments'], default=str),
            'call_id': call['call_id'],
        }

    @staticmethod
    def _text_carry(text: str) -> dict:
        """Return the assistant item carrying an answer into the history."""
        return {'role': 'assistant', 'content': [{'type': 'output_text', 'text': text}]}

    @staticmethod
    def _text_from_content(content) -> str:
        """Flatten a content value, a string or a list of blocks, into plain text."""
        if isinstance(content, str):
            return content
        return ''.join(block.get('text') or '' for block in content or [])

    @classmethod
    def _system_text(cls, inputs: list[dict]) -> str:
        """Join the text of the system items among the inputs."""
        return '\n\n'.join(
            text
            for item in inputs or []
            if item.get('role') == 'system'
            and (text := cls._text_from_content(item.get('content')))
        )

    @classmethod
    def _content_parts(cls, content) -> list[dict]:
        """Convert canonical content, a string or a list of blocks, into wire parts."""
        if isinstance(content, str):
            return [cls._text_part(content)]
        parts = []
        for chunk in content or []:
            if not isinstance(chunk, dict):
                continue
            if chunk.get('type') == 'muk_ai_attachment':
                parts.append(cls._attachment_part(chunk))
            elif chunk.get('text'):
                parts.append(cls._text_part(chunk['text']))
        return parts

    @staticmethod
    def _text_part(text: str) -> dict:
        """Return the wire part carrying a text."""
        raise NotImplementedError

    @classmethod
    def _attachment_part(cls, block: dict) -> dict:
        """Return the wire part carrying an attachment block."""
        raise NotImplementedError

    @staticmethod
    def _append_turn(turns: list[dict], key: str, role: str, part: dict) -> None:
        """Append a part under ``key``, merged into a last turn of the same role."""
        if turns and turns[-1]['role'] == role:
            turns[-1][key].append(part)
        else:
            turns.append({'role': role, key: [part]})

    @staticmethod
    def _attachment_text(block: dict) -> str:
        """Render an attachment the vendor does not take natively as plain text."""
        text = block.get('inline_text') or ''
        if block.get('truncated'):
            text += '\n[truncated]'
        filename = block.get('filename') or 'attachment'
        mimetype = block.get('mimetype') or 'application/octet-stream'
        return f'--- File: {filename} ({mimetype}) ---\n{text}'

    @staticmethod
    def _unique_tools(tools_schema) -> Iterator[tuple[str, str, dict]]:
        """Yield the name, description and parameters of each distinct tool."""
        seen = set()
        for tool in tools_schema or []:
            if (name := tool['name']) not in seen:
                seen.add(name)
                yield (
                    name,
                    tool.get('description') or '',
                    tool.get('parameters') or {'type': 'object', 'properties': {}},
                )

    @classmethod
    def _carried_state(cls, item) -> dict:
        """Return this provider's own private state carried on an input item.

        An adapter only ever sees the slot filed under its own name, so state
        another vendor signed is invisible here rather than merely unused.
        """
        if not isinstance(item, dict):
            return {}
        return (item.get(PROVIDER_STATE_KEY) or {}).get(cls.name) or {}

    @classmethod
    def _carry_state(cls, carry: dict, state: dict) -> dict:
        """Return the carry item with this provider's private state attached.

        Opaque material a provider replays to itself, a Gemini
        ``thoughtSignature``, lives here, so :meth:`_wire_items` drops it when
        another vendor gets the conversation.
        """
        by_provider = {**(carry.get(PROVIDER_STATE_KEY) or {}), cls.name: state}
        return {**carry, PROVIDER_STATE_KEY: by_provider}

    @classmethod
    def _wire_items(cls, inputs) -> list:
        """Return the input items without any key the wire must not see.

        Canonical items carry session bookkeeping under an underscore prefix
        and provider-private state under :data:`PROVIDER_STATE_KEY`.
        """
        return [
            {
                key: value
                for key, value in item.items()
                if not key.startswith('_') and key != PROVIDER_STATE_KEY
            }
            if isinstance(item, dict)
            else item
            for item in inputs or []
        ]

    @staticmethod
    def _parse_tool_arguments(raw) -> tuple[dict, str | None]:
        """Parse tool-call arguments, returning ``(args, error_message)``."""
        if isinstance(raw, dict):
            return raw, None
        raw = raw or '{}'
        try:
            return json.loads(raw), None
        except ValueError as exc:
            return {}, f'Malformed JSON arguments: {exc}. Raw: {raw!r}'

    @staticmethod
    def _call_on_delta(on_delta, kind: str, payload) -> None:
        """Invoke the streaming delta callback, swallowing handler failures.

        :raise StreamCancelled: when cancelled or the DB transaction has failed.
        """
        if not callable(on_delta):
            return
        try:
            on_delta(kind, payload)
        except StreamCancelled:
            raise
        except (
            psycopg2.errors.InFailedSqlTransaction,
            psycopg2.errors.SerializationFailure,
        ) as exc:
            raise StreamCancelled() from exc
        except Exception:
            _logger.exception('on_delta handler failed')

    @staticmethod
    def _usage(
        input_tokens: int = 0,
        output_tokens: int = 0,
        cache_read_tokens: int = 0,
        cache_write_tokens: int = 0,
    ) -> dict:
        """Build a normalized token usage dict, defaulting falsy values to zero.

        ``input_tokens`` is the full prompt size; the cache counts are its subsets
        billed at the cache read and write rates.
        """
        return {
            'input_tokens': input_tokens or 0,
            'output_tokens': output_tokens or 0,
            'cache_read_tokens': cache_read_tokens or 0,
            'cache_write_tokens': cache_write_tokens or 0,
        }

    def _apply_truncation(
        self,
        result: dict,
        on_delta: Callable | None = None,
        limit: int | None = None,
    ) -> dict:
        """Append a truncation notice to a token-capped result and forward it.

        The partial text and usage are kept, so cost still accrues.

        :param limit: the output-token cap that was hit, when known
        """
        if limit:
            notice = self.env._(
                'Response truncated: the output hit the configured Max Tokens '
                'limit of %(limit)s tokens (including any reasoning). Raise '
                'the Max Tokens setting on the %(provider)s provider to allow '
                'longer responses.',
                limit=limit,
                provider=self.label,
            )
        else:
            notice = self.env._(
                'Response truncated: the model reached its maximum output '
                'token limit before finishing.'
            )
        notice = f'_{notice}_'
        self._call_on_delta(on_delta, 'text', {'delta': f'\n\n{notice}'})
        result['text'] = f'{result["text"]}\n\n{notice}'.strip()
        return result

    def _raise_stream_error(self, error: dict, *code_keys: str) -> None:
        """Raise the error event of a stream, naming the first code it carries.

        :raise UserError: always.
        """
        message = error.get('message') or 'Unknown streaming error'
        if code := next(filter(None, map(error.get, code_keys)), None):
            message = f'{message} (code: {code})'
        self._raise(message)

    def _raise(self, error) -> None:
        """Wrap a provider error into a user-facing :class:`UserError`.

        :raise UserError: always.
        """
        raise UserError(
            self.env._(
                'AI provider %(provider)s request failed: %(error)s',
                provider=self.name,
                error=str(error)[:500],
            )
        )
