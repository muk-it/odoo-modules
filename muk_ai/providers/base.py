import json
import logging

import psycopg2
import requests

from odoo import _
from odoo.exceptions import UserError

from odoo.addons.muk_ai.tools import StreamCancelled

_logger = logging.getLogger(__name__)


class ProviderBase:

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
        api_key='',
        request_timeout=60,
        idle_timeout=45,
        max_tokens=4096
    ):
        self._api_key = api_key or ''
        self.request_timeout = request_timeout
        self.idle_timeout = idle_timeout
        self.max_tokens = max_tokens

    # ----------------------------------------------------------
    # Config
    # ----------------------------------------------------------

    @property
    def api_url(self):
        return self.default_url

    @property
    def api_key(self):
        if not self._api_key:
            raise UserError(_(
                '%(provider)s API key is not configured.', provider=self.label,
            ))
        return self._api_key

    def model_for(self, override=None):
        return override or self.default_model

    # ----------------------------------------------------------
    # Contract
    # ----------------------------------------------------------

    def headers(self):
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
    ):
        raise NotImplementedError

    def test_connection(self):
        payload = self.request(
            inputs=[
                {'role': 'system', 'content': [{'type': 'input_text', 'text': 'Reply with a single word.'}]},
                {'role': 'user', 'content': [{'type': 'input_text', 'text': 'Say: ok'}]},
            ],
        )
        if not payload.get('text'):
            raise UserError(_(
                'AI provider returned an empty response during the connection test.'
            ))
        return True

    # ----------------------------------------------------------
    # HTTP
    # ----------------------------------------------------------

    def _post_json(self, path, body):
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

    def _post_stream(self, path, body):
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
                    self._raise(_(
                        'Stream idle for %ss — aborted',
                        read_timeout
                    ))
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
        except StreamCancelled:
            raise
        finally:
            try:
                response.close()
            except Exception:
                pass

    # ----------------------------------------------------------
    # Error
    # ----------------------------------------------------------

    @staticmethod
    def _parse_tool_arguments(raw):
        if isinstance(raw, dict):
            return raw, None
        raw = raw or '{}'
        try:
            return json.loads(raw), None
        except ValueError as exc:
            return {}, f'Malformed JSON arguments: {exc}. Raw: {raw!r}'

    @staticmethod
    def _call_on_delta(on_delta, kind, payload):
        if not callable(on_delta):
            return
        try:
            on_delta(kind, payload)
        except StreamCancelled:
            raise
        except (
            psycopg2.errors.InFailedSqlTransaction,
            psycopg2.errors.SerializationFailure,
        ):
            raise StreamCancelled()
        except Exception:
            _logger.exception('on_delta handler failed')

    @staticmethod
    def _usage(input_tokens=0, output_tokens=0, cached_tokens=0):
        return {
            'input_tokens': input_tokens or 0,
            'output_tokens': output_tokens or 0,
            'cached_tokens': cached_tokens or 0,
        }

    def _raise(self, error):
        raise UserError(_(
            'AI provider %(provider)s request failed: %(error)s',
            provider=self.name, error=str(error)[:500],
        ))
