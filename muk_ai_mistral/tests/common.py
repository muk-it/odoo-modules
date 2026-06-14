import json
from unittest.mock import MagicMock

from odoo.tests.common import TransactionCase

from odoo.addons.muk_ai_mistral.providers.mistral import MistralProvider


class MistralTestCommon(TransactionCase):

    # ----------------------------------------------------------
    # Setup
    # ----------------------------------------------------------

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.provider = cls.env.ref('muk_ai_mistral.provider_mistral')
        cls.provider.sudo().api_key = 'test-key'

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    def _make_client(self, **overrides):
        return MistralProvider(
            api_key=overrides.pop('api_key', 'test-key'),
            max_tokens=overrides.pop('max_tokens', 4096),
            request_timeout=overrides.pop('request_timeout', 60),
        )

    def _mock_http_response(self, payload=None, status_code=200, content=b''):
        response = MagicMock()
        response.status_code = status_code
        response.json.return_value = payload or {}
        response.content = content
        response.raise_for_status.return_value = None
        return response

    def _message_output(self, content):
        return {
            'object': 'entry',
            'type': 'message.output',
            'role': 'assistant',
            'content': content,
        }

    def _function_call(self, call_id, name, args):
        return {
            'object': 'entry',
            'type': 'function.call',
            'tool_call_id': call_id,
            'name': name,
            'arguments': json.dumps(args),
        }

    def _conv_response(self, outputs, usage=None):
        return {
            'object': 'conversation.response',
            'conversation_id': 'conv_test',
            'outputs': outputs,
            'usage': usage or {
                'prompt_tokens': 3,
                'completion_tokens': 2,
                'total_tokens': 5,
            },
        }

    def _text_response(self, text='ok'):
        return self._conv_response([self._message_output(text)])

    def _sse_lines(self, payloads):
        lines = []
        for payload in payloads:
            lines.append('event: ' + payload.get('type', 'message'))
            lines.append('data: ' + json.dumps(payload))
            lines.append('')
        return lines
