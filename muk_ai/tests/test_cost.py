from __future__ import annotations

from contextlib import AbstractContextManager
from unittest.mock import MagicMock, patch

from odoo.addons.muk_ai.tests.common import AITestCommon


class TestSessionCostAccrual(AITestCommon):
    """Verify token-usage cost accrual on sessions."""

    # ----------------------------------------------------------
    # Setup
    # ----------------------------------------------------------

    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls.model = cls.env['muk_ai.model'].create(
            {
                'name': 'Test',
                'provider_id': cls.provider.id,
                'technical_name': 'test-cost-model',
                'context_window': 10_000_000,
                'input_rate': 1.0,
                'output_rate': 2.0,
                'cache_read_rate': 0.0,
            }
        )
        cls.provider.default_model_id = cls.model.id

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    def _payload(
        self,
        text: str = 'ok',
        input_tokens: int = 10_000,
        output_tokens: int = 5_000,
    ) -> dict:
        """Build a provider payload carrying assistant text and token usage."""
        return {
            'text': text,
            'tool_calls': [],
            'carry_inputs': [
                {
                    'type': 'message',
                    'content': [{'type': 'output_text', 'text': text}],
                }
            ],
            'usage': {
                'input_tokens': input_tokens,
                'output_tokens': output_tokens,
                'cache_read_tokens': 0,
            },
        }

    def _patch_provider(
        self, payloads: list[dict]
    ) -> AbstractContextManager[MagicMock]:
        """Patch the provider to pop one payload per LLM request.

        :raise AssertionError: When more requests are made than payloads given.
        """
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

    # ----------------------------------------------------------
    # Tests
    # ----------------------------------------------------------

    def test_cost_accrues_on_completion(self):
        session = self.env['muk_ai.session'].create(
            {'name': 'cost-one', 'agent_id': False}
        )
        with self._patch_provider(
            [
                self._payload(
                    input_tokens=1_000_000,
                    output_tokens=500_000,
                )
            ]
        ):
            snapshot = session.start('hi')
        self.assertAlmostEqual(session.total_input_cost, 1.0)
        self.assertAlmostEqual(session.total_output_cost, 1.0)
        self.assertAlmostEqual(session.total_cost, 2.0)
        self.assertAlmostEqual(snapshot['total_input_cost'], 1.0)
        self.assertAlmostEqual(snapshot['total_output_cost'], 1.0)
        self.assertAlmostEqual(snapshot['total_cost'], 2.0)

    def test_cost_accumulates_across_rounds(self):
        session = self.env['muk_ai.session'].create(
            {'name': 'cost-cum', 'agent_id': False}
        )
        with self._patch_provider(
            [
                self._payload(
                    input_tokens=1_000_000,
                    output_tokens=500_000,
                )
            ]
        ):
            session.start('first')
        first_total = session.total_cost
        with self._patch_provider(
            [
                self._payload(
                    input_tokens=2_000_000,
                    output_tokens=100_000,
                )
            ]
        ):
            session.send_message('again')
        self.assertGreater(session.total_cost, first_total)
        self.assertAlmostEqual(session.total_cost - first_total, 2.2)

    def test_cost_stays_zero_when_no_default_model(self):
        self.provider.default_model_id = False
        self.model.active = False
        session = self.env['muk_ai.session'].create(
            {'name': 'no-price', 'agent_id': False}
        )
        with self._patch_provider([self._payload()]):
            session.start('hi')
        self.assertEqual(session.total_cost, 0.0)
