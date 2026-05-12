import json

from contextlib import contextmanager
from unittest.mock import patch

from odoo.tests.common import TransactionCase


class BridgeTestCommon(TransactionCase):
    """Shared helpers for muk_ai_enterprise tests.

    Mirrors muk_ai's `tests/common.py` but stays self-contained so the
    bridge suite is runnable with just `-i muk_ai_enterprise`. Mocks the
    OpenAI provider so no real LLM calls are ever issued.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.provider = cls.env.ref('muk_ai.provider_openai')
        cls.provider.sudo().api_key = 'test-key'

    # ----------------------------------------------------------
    # Provider mocking
    # ----------------------------------------------------------

    def _patch_provider(self, payloads, captured=None):
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
                captured.append({
                    'inputs': inputs,
                    'tools_schema': tools_schema,
                })
            if not remaining:
                raise AssertionError('No more mocked responses')
            return remaining.pop(0)

        return patch.object(
            type(self.provider),
            '_request_responses',
            autospec=True,
            side_effect=fake,
        )

    def _text_payload(self, text='ok'):
        return {
            'text': text,
            'tool_calls': [],
            'carry_inputs': [{
                'type': 'message',
                'content': [{'type': 'output_text', 'text': text}],
            }],
            'usage': {'input_tokens': 3, 'output_tokens': 1},
        }

    def _tool_payload(self, name, arguments, call_id='call_1'):
        return {
            'text': '',
            'tool_calls': [{
                'call_id': call_id,
                'name': name,
                'arguments': arguments,
            }],
            'carry_inputs': [{
                'type': 'function_call',
                'name': name,
                'arguments': json.dumps(arguments),
                'call_id': call_id,
            }],
            'usage': {'input_tokens': 4, 'output_tokens': 2},
        }

    # ----------------------------------------------------------
    # Misc
    # ----------------------------------------------------------

    @contextmanager
    def _mute_logger(self, *names):
        try:
            from odoo.tests.common import warmup  # noqa: F401
        except Exception:
            pass
        import logging
        loggers = [logging.getLogger(n) for n in names]
        previous = [(lg, lg.disabled) for lg in loggers]
        for lg in loggers:
            lg.disabled = True
        try:
            yield
        finally:
            for lg, was in previous:
                lg.disabled = was
