from __future__ import annotations

import contextlib
import json
import logging
from collections.abc import Iterator

import psycopg2
import requests

from odoo import _
from odoo.exceptions import UserError

from odoo.addons.muk_ai.tools import StreamCancelled

_logger = logging.getLogger(__name__)


class ProviderBase:
    """Base class for AI provider adapters: config, HTTP, and streaming helpers."""

    name = ''
    label = ''
    default_model = ''
    default_url = ''

    supports_web_search = False
    supports_image_generation = False
    supports_code_interpreter = False

    # ----------------------------------------------------------
    # Setup
    # ----------------------------------------------------------

    def __init__(
        self,
        api_key: str = '',
        request_timeout: int = 60,
        idle_timeout: int = 45,
        max_tokens: int = 4096,
    ) -> None:
        """Store the API key and request/streaming timeouts for this provider."""
        self._api_key = api_key or ''
        self.request_timeout = request_timeout
        self.idle_timeout = idle_timeout
        self.max_tokens = max_tokens

    # ----------------------------------------------------------
    # Config
    # ----------------------------------------------------------

    @property
    def api_url(self) -> str:
        """Return the base API URL for this provider."""
        return self.default_url

    @property
    def api_key(self) -> str:
        """Return the configured API key.

        :raise UserError: when no API key is configured.
        """
        if not self._api_key:
            raise UserError(
                _(
                    '%(provider)s API key is not configured.',
                    provider=self.label,
                )
            )
        return self._api_key

    def model_for(self, override: str | None = None) -> str:
        """Return the override model when given, else the provider default."""
        return override or self.default_model

    # ----------------------------------------------------------
    # Contract
    # ----------------------------------------------------------

    def headers(self) -> dict:
        """Return the HTTP headers for a provider request."""
        raise NotImplementedError

    def request(
        self,
        inputs,
        tools_schema=None,
        text_schema=None,
        on_delta=None,
        model=None,
        enable_web_search=False,
        enable_image_generation=False,
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

    # ----------------------------------------------------------
    # HTTP
    # ----------------------------------------------------------

    def _post_json(self, path: str, body: dict) -> dict:
        """POST a JSON body and return the decoded response.

        :raise UserError: on HTTP or transport errors.
        """
        try:
            response = requests.post(
                f'{self.api_url}{path}',
                headers=self.headers(),
                json=body,
                timeout=self.request_timeout,
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
            response = requests.post(
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
        except Exception:  # noqa: BLE001 — delta handler must never break the stream
            _logger.exception('on_delta handler failed')

    @staticmethod
    def _usage(
        input_tokens: int = 0,
        output_tokens: int = 0,
        cached_tokens: int = 0,
    ) -> dict:
        """Build a normalized token usage dict, defaulting falsy values to zero."""
        return {
            'input_tokens': input_tokens or 0,
            'output_tokens': output_tokens or 0,
            'cached_tokens': cached_tokens or 0,
        }

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
