from __future__ import annotations

import json
from unittest.mock import MagicMock

from odoo.tests.common import TransactionCase

from odoo.addons.muk_ai_mistral.providers.mistral import MistralProvider


class MistralTestCommon(TransactionCase):
    """Shared setup and payload builders for the Mistral provider tests."""

    # ----------------------------------------------------------
    # Setup
    # ----------------------------------------------------------

    @classmethod
    def setUpClass(cls) -> None:
        """Seed the Mistral provider record with a dummy API key."""
        super().setUpClass()
        cls.provider = cls.env.ref('muk_ai_mistral.provider_mistral')
        cls.provider.sudo().api_key = 'test-key'

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    def _make_client(self, **overrides) -> MistralProvider:
        """Build a standalone provider client with optional overrides."""
        return MistralProvider(
            env=self.env,
            api_key=overrides.pop('api_key', 'test-key'),
            max_tokens=overrides.pop('max_tokens', 4096),
            request_timeout=overrides.pop('request_timeout', 60),
        )

    def _mock_http_response(
        self,
        payload: dict | None = None,
        status_code: int = 200,
        content: bytes = b'',
    ) -> MagicMock:
        """Build a mocked ``requests`` response with the given payload."""
        response = MagicMock()
        response.status_code = status_code
        response.json.return_value = payload or {}
        response.content = content
        response.raise_for_status.return_value = None
        return response

    def _message_output(self, content) -> dict:
        """Build an assistant ``message.output`` conversation entry."""
        return {
            'object': 'entry',
            'type': 'message.output',
            'role': 'assistant',
            'content': content,
        }

    def _function_call(self, call_id: str, name: str, args: dict) -> dict:
        """Build a ``function.call`` conversation entry."""
        return {
            'object': 'entry',
            'type': 'function.call',
            'tool_call_id': call_id,
            'name': name,
            'arguments': json.dumps(args),
        }

    def _conv_response(self, outputs: list, usage: dict | None = None) -> dict:
        """Wrap output entries in a full conversation response payload."""
        return {
            'object': 'conversation.response',
            'conversation_id': 'conv_test',
            'outputs': outputs,
            'usage': usage
            or {
                'prompt_tokens': 3,
                'completion_tokens': 2,
                'total_tokens': 5,
            },
        }

    def _text_response(self, text: str = 'ok') -> dict:
        """Build a conversation response carrying a single text message."""
        return self._conv_response([self._message_output(text)])

    def _sse_lines(self, payloads: list) -> list:
        """Render payloads as raw SSE ``event``/``data`` lines."""
        lines = []
        for payload in payloads:
            lines.append('event: ' + payload.get('type', 'message'))
            lines.append('data: ' + json.dumps(payload))
            lines.append('')
        return lines
