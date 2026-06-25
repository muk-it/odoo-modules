from __future__ import annotations

import json
from unittest.mock import patch

from odoo.tests.common import TransactionCase


class BridgeTestCommon(TransactionCase):
    """Provide provider mocking helpers for the EE bridge test suite."""

    # ----------------------------------------------------------
    # Setup
    # ----------------------------------------------------------

    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls.provider = cls.env.ref('muk_ai.provider_openai')
        cls.provider.sudo().api_key = 'test-key'

    # ----------------------------------------------------------
    # Provider
    # ----------------------------------------------------------

    def _patch_provider(self, payloads: list[dict], captured: list | None = None):
        """Return a patch of the provider request returning queued payloads."""
        remaining = list(payloads)

        def fake(
            self_arg,
            inputs,
            tools_schema=None,
            text_schema=None,
            on_delta=None,
            model=None,
            **kwargs,
        ):
            if captured is not None:
                captured.append(
                    {
                        'inputs': inputs,
                        'tools_schema': tools_schema,
                    }
                )
            if not remaining:
                msg = 'No more mocked responses'
                raise AssertionError(msg)
            return remaining.pop(0)

        return patch.object(
            type(self.provider),
            '_request_responses',
            autospec=True,
            side_effect=fake,
        )

    def _text_payload(self, text: str = 'ok') -> dict:
        """Return a mocked text-only provider response payload."""
        return {
            'text': text,
            'tool_calls': [],
            'carry_inputs': [
                {
                    'type': 'message',
                    'content': [{'type': 'output_text', 'text': text}],
                }
            ],
            'usage': {'input_tokens': 3, 'output_tokens': 1},
        }

    def _tool_payload(
        self, name: str, arguments: dict, call_id: str = 'call_1'
    ) -> dict:
        """Return a mocked tool-call provider response payload."""
        return {
            'text': '',
            'tool_calls': [
                {
                    'call_id': call_id,
                    'name': name,
                    'arguments': arguments,
                }
            ],
            'carry_inputs': [
                {
                    'type': 'function_call',
                    'name': name,
                    'arguments': json.dumps(arguments),
                    'call_id': call_id,
                }
            ],
            'usage': {'input_tokens': 4, 'output_tokens': 2},
        }
