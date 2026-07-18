from __future__ import annotations

from contextlib import contextmanager
from unittest.mock import MagicMock, patch

from odoo import models
from odoo.tests.common import TransactionCase, tagged

from odoo.addons.muk_ai.providers.base import _REJECTED_REASONING_MODELS


@tagged('post_install', '-at_install')
class AITestCommon(TransactionCase):
    """Shared setup and mocking helpers for the AI provider/session tests."""

    # ----------------------------------------------------------
    # Setup
    # ----------------------------------------------------------

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.provider = cls.env.ref('muk_ai.provider_openai')
        cls.provider.sudo().write({'api_key': 'test-key', 'active': True})
        cls.provider_anthropic = cls.env.ref('muk_ai.provider_anthropic')
        cls.provider_anthropic.sudo().api_key = 'test-key'
        cls.provider_google = cls.env.ref('muk_ai.provider_google')
        cls.provider_google.sudo().api_key = 'test-key'
        cls.env.company.default_ai_provider_id = cls.provider

    def setUp(self):
        super().setUp()
        _REJECTED_REASONING_MODELS.clear()

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    def _create_model(self, technical_name: str, **values) -> models.BaseModel:
        """Create a catalog model record for ``technical_name`` on the provider."""
        return self.env['muk_ai.model'].create(
            {
                'name': technical_name,
                'provider_id': self.provider.id,
                'technical_name': technical_name,
                'context_window': 400000,
                'input_rate': 1.0,
                'output_rate': 1.0,
                **values,
            }
        )

    @classmethod
    def _mark_sensitive(cls, *model_names: str) -> None:
        """Flag the given models as AI-sensitive for approval tests."""
        cls.env['ir.model'].sudo().search(
            [('model', 'in', list(model_names))],
        ).write({'ai_sensitive': True})

    def _mock_http_response(self, payload: dict, status_code: int = 200) -> MagicMock:
        """Build a mocked HTTP response returning the given JSON payload."""
        response = MagicMock()
        response.status_code = status_code
        response.json.return_value = payload
        response.raise_for_status.return_value = None
        return response

    @contextmanager
    def _mock_responses(self, payloads: list):
        """Patch the provider to pop one mocked payload per LLM request."""
        remaining = list(payloads)

        def fake(self_arg, *args, **kwargs):
            if not remaining:
                msg = 'No more mocked responses'
                raise AssertionError(msg)
            return remaining.pop(0)

        with patch.object(
            type(self.provider),
            '_request_responses',
            autospec=True,
            side_effect=fake,
        ) as mock:
            yield mock

    def _make_text_response(self, text: str = 'ok') -> dict:
        """Build a provider payload emitting plain assistant text."""
        return {
            'text': text,
            'tool_calls': [],
            'carry_inputs': [],
            'usage': {'input_tokens': 10, 'output_tokens': 5, 'cache_read_tokens': 0},
        }
