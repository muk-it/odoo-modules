from __future__ import annotations

import contextlib
import json
import logging
from collections.abc import Callable, Iterator

import psycopg2
import requests

from odoo import _, models
from odoo.api import Environment
from odoo.exceptions import UserError

from odoo.addons.muk_ai.providers.region import Region
from odoo.addons.muk_ai.tools import StreamCancelled, http_session

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
    # Config
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

        An adapter whose endpoint may legitimately need none — a local Ollama
        behind the OpenAI-compatible wire — overrides this, and :attr:`api_key`
        follows it, so the two can never disagree.
        """
        return bool(self._api_key)

    @property
    def api_key(self) -> str:
        """Return the configured API key.

        :raise UserError: when no API key is configured.
        """
        if not self.authenticated:
            raise UserError(
                _(
                    '%(provider)s API key is not configured.',
                    provider=self.label,
                )
            )
        return self._api_key

    @property
    def request_timeout(self) -> int:
        """Return the provider request timeout in seconds."""
        return self.provider.request_timeout

    @property
    def idle_timeout(self) -> int:
        """Return the streaming idle timeout in seconds."""
        return self.provider.idle_timeout

    @property
    def image_timeout(self) -> int:
        """Return the image generation timeout in seconds."""
        return self.provider.image_timeout

    @property
    def max_tokens(self) -> int:
        """Return the completion token limit per request."""
        return self.provider.max_tokens

    def model_for(self, override: str | None = None) -> str:
        """Return the override, the record default model, or the class default."""
        return (
            override
            or self.provider._default_model('chat').technical_name
            or self.default_model
        )

    # ----------------------------------------------------------
    # Contract
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
        inputs,
        tools_schema=None,
        text_schema=None,
        on_delta=None,
        model=None,
        enable_web_search=False,
        enable_code_interpreter=False,
        extra=None,
    ) -> dict:
        """Run an inference request against the provider and return its result."""
        raise NotImplementedError

    def test_connection(self) -> bool:
        """Issue a minimal request to verify the provider responds.

        :raise UserError: when the provider returns an empty response.
        """
        payload = self.request(
            inputs=[
                {
                    'role': 'system',
                    'content': [
                        {'type': 'input_text', 'text': 'Reply with a single word.'}
                    ],
                },
                {
                    'role': 'user',
                    'content': [{'type': 'input_text', 'text': 'Say: ok'}],
                },
            ],
        )
        if not payload.get('text'):
            raise UserError(
                _('AI provider returned an empty response during the connection test.')
            )
        return True

    def generate_image(
        self,
        model: str,
        prompt: str,
        options: dict | None = None,
    ) -> dict:
        """Render one image with a catalogued image model of this provider.

        Defaults to the OpenAI ``/images/generations`` wire. ``gpt-image-*``
        models reject ``response_format`` and always answer base64.

        :raise UserError: when the request fails or no image data comes back
        """
        body = {
            'model': model,
            'prompt': prompt,
            **{key: value for key, value in (options or {}).items() if value},
        }
        if not model.startswith('gpt-image'):
            body['response_format'] = 'b64_json'
        try:
            response = self._http_session().post(
                f'{self.api_url}/images/generations',
                headers=self.headers(),
                json=body,
                timeout=self.image_timeout,
            )
            response.raise_for_status()
        except requests.HTTPError as error:
            self._raise(getattr(error.response, 'text', '') or str(error))
        except requests.RequestException as error:
            self._raise(error)
        payload = response.json()
        entry = next(iter(payload.get('data') or []), None) or {}
        if not (data_b64 := entry.get('b64_json')):
            self._raise(_('no image data returned'))
        return {
            'data_b64': data_b64,
            'mimetype': 'image/png',
            'revised_prompt': entry.get('revised_prompt') or '',
            'usage': {'images': 1},
        }

    # ----------------------------------------------------------
    # HTTP
    # ----------------------------------------------------------

    _http_session = staticmethod(http_session)

    def _post_json(self, path: str, body: dict, timeout: int | None = None) -> dict:
        """POST a JSON body and return the decoded response.

        :param timeout: budget in seconds, defaulting to the chat request
            timeout; a route that outlives it (image rendering) passes its own.
        :raise UserError: on HTTP or transport errors.
        """
        try:
            response = self._http_session().post(
                f'{self.api_url}{path}',
                headers=self.headers(),
                json=body,
                timeout=timeout or self.request_timeout,
            )
            response.raise_for_status()
        except requests.HTTPError as error:
            self._raise(getattr(error.response, 'text', '') or str(error))
        except requests.RequestException as error:
            self._raise(error)
        return response.json()

    def _post_stream(self, path: str, body: dict) -> Iterator[dict]:
        """POST a JSON body and yield decoded SSE ``data:`` payloads.

        :raise UserError: on HTTP, transport, or stream-idle errors.
        """
        read_timeout = self.idle_timeout
        try:
            response = self._http_session().post(
                f'{self.api_url}{path}',
                headers=self.headers(),
                json=body,
                timeout=read_timeout,
                stream=True,
            )
            response.raise_for_status()
        except requests.HTTPError as error:
            self._raise(getattr(error.response, 'text', '') or str(error))
        except requests.RequestException as error:
            self._raise(error)
        response.encoding = 'utf-8'
        line_iter = response.iter_lines(decode_unicode=True)
        try:
            while True:
                try:
                    raw_line = next(line_iter)
                except StopIteration:
                    break
                except requests.exceptions.ReadTimeout:
                    self._raise(_('Stream idle for %ss — aborted', read_timeout))
                except requests.RequestException as error:
                    self._raise(error)
                if not raw_line or not raw_line.startswith('data:'):
                    continue
                payload = raw_line[5:].strip()
                if not payload or payload == '[DONE]':
                    continue
                try:
                    yield json.loads(payload)
                except ValueError:
                    continue
        finally:
            with contextlib.suppress(Exception):
                response.close()

    # ----------------------------------------------------------
    # Reasoning
    # ----------------------------------------------------------

    def _invoke_with_reasoning_retry(
        self,
        model: str,
        invoke: Callable,
        on_delta: Callable | None,
        stages: tuple,
    ) -> dict:
        """Run ``invoke``, retrying without rejected reasoning config.

        When the provider rejects the request with a message naming the
        reasoning config (any word in :attr:`reasoning_error_tokens`,
        the wire vocabulary each adapter declares — without declared
        tokens no retry fires), the ``(config, keys)`` stages apply in
        order — pop ``keys`` from ``config`` and retry — so the answer
        is still served. The logged warning tells the admin what to
        correct in the model catalog; requests keep paying one rejected
        attempt until it is. No retry fires after streamed deltas — a
        replay would duplicate visible output and re-run server-side
        tools.
        """
        delivered = False

        def guarded(kind, data):
            nonlocal delivered
            delivered = True
            return on_delta(kind, data)

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

    # ----------------------------------------------------------
    # Carry state
    # ----------------------------------------------------------

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

        Opaque material a provider must replay to itself — a Gemini
        ``thoughtSignature`` — belongs here, not on the canonical item, so
        :meth:`_wire_items` drops it when another vendor gets the conversation.
        """
        by_provider = {**(carry.get(PROVIDER_STATE_KEY) or {}), cls.name: state}
        return {**carry, PROVIDER_STATE_KEY: by_provider}

    @classmethod
    def _wire_items(cls, inputs) -> list:
        """Return the input items without any key the wire must not see.

        Canonical items carry session bookkeeping under an underscore prefix
        and provider-private state under :data:`PROVIDER_STATE_KEY`; neither
        may ride along into a request.
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

    # ----------------------------------------------------------
    # Error
    # ----------------------------------------------------------

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

        ``input_tokens`` is always the FULL prompt size including cache-read
        and cache-written tokens; ``cache_read_tokens`` and
        ``cache_write_tokens`` are the subsets billed at the cache read and
        write rates.
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

        Truncation is an honest outcome, not a failure: the partial text and
        the captured usage are kept so cost still accrues, and the notice
        names the output-token cap to raise instead of surfacing a generic
        empty-output error.

        :param limit: the output-token cap that was hit, when known.
        """
        if limit:
            notice = _(
                'Response truncated: the output hit the configured Max Tokens '
                'limit of %(limit)s tokens (including any reasoning). Raise '
                'the Max Tokens setting on the %(provider)s provider to allow '
                'longer responses.',
                limit=limit,
                provider=self.label,
            )
        else:
            notice = _(
                'Response truncated: the model reached its maximum output '
                'token limit before finishing.'
            )
        notice = f'_{notice}_'
        self._call_on_delta(on_delta, 'text', {'delta': f'\n\n{notice}'})
        result['text'] = f'{result["text"]}\n\n{notice}'.strip()
        return result

    def _raise(self, error) -> None:
        """Wrap a provider error into a user-facing :class:`UserError`.

        :raise UserError: always.
        """
        raise UserError(
            _(
                'AI provider %(provider)s request failed: %(error)s',
                provider=self.name,
                error=str(error)[:500],
            )
        )
