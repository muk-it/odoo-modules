from contextlib import contextmanager
from unittest.mock import MagicMock, patch

from odoo.tests.common import TransactionCase


class AITestCommon(TransactionCase):

    # ----------------------------------------------------------
    # Setup
    # ----------------------------------------------------------

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.provider = cls.env.ref('muk_ai.provider_openai')
        cls.provider.sudo().api_key = 'test-key'
        cls.provider_anthropic = cls.env.ref('muk_ai.provider_anthropic')
        cls.provider_anthropic.sudo().api_key = 'test-key'
        cls.provider_google = cls.env.ref('muk_ai.provider_google')
        cls.provider_google.sudo().api_key = 'test-key'
        cls.env.company.default_ai_provider_id = cls.provider

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    @classmethod
    def _mark_sensitive(cls, *model_names):
        cls.env['ir.model'].sudo().search(
            [('model', 'in', list(model_names))],
        ).write({'ai_sensitive': True})

    def _mock_http_response(self, payload, status_code=200):
        response = MagicMock()
        response.status_code = status_code
        response.json.return_value = payload
        response.raise_for_status.return_value = None
        return response

    @contextmanager
    def _mock_responses(self, payloads):
        remaining = list(payloads)

        def fake(self_arg, *args, **kwargs):
            if not remaining:
                raise AssertionError('No more mocked responses')
            return remaining.pop(0)

        with patch.object(
            type(self.provider),
            '_request_responses',
            autospec=True,
            side_effect=fake,
        ) as mock:
            yield mock

    def _make_text_response(self, text='ok'):
        return {
            'text': text,
            'tool_calls': [],
            'carry_inputs': [],
            'usage': {'input_tokens': 10, 'output_tokens': 5, 'cached_tokens': 0},
        }
