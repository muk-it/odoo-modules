from unittest.mock import patch

from odoo.addons.muk_ai.tests.common import AITestCommon


class TestSessionCostAccrual(AITestCommon):

    # ----------------------------------------------------------
    # Setup
    # ----------------------------------------------------------

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # Large context window so the deliberately large per-round token
        # counts below (chosen for clean cost math) stay well under the
        # auto-compaction threshold (last_input_tokens / window >=
        # COMPACT_AUTO_RATIO). Otherwise the 1M-token first round would trip
        # _maybe_auto_compact on the next send and consume a mocked response.
        cls.model = cls.env['muk_ai.model'].create({
            'name': 'Test',
            'provider_id': cls.provider.id,
            'technical_name': 'test-cost-model',
            'context_window': 100_000_000,
            'input_rate': 1.0,
            'output_rate': 2.0,
            'cached_rate': 0.0,
        })
        cls.provider.default_model_id = cls.model.id

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    def _payload(self, text='ok', input_tokens=10_000, output_tokens=5_000):
        return {
            'text': text,
            'tool_calls': [],
            'carry_inputs': [{
                'type': 'message',
                'content': [{'type': 'output_text', 'text': text}],
            }],
            'usage': {
                'input_tokens': input_tokens,
                'output_tokens': output_tokens,
                'cached_tokens': 0,
            },
        }

    def _patch_provider(self, payloads):
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
                raise AssertionError('No more mocked responses')
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
        session = self.env['muk_ai.session'].create({'name': 'cost-one', 'agent_id': False})
        with self._patch_provider([self._payload(
            input_tokens=1_000_000, output_tokens=500_000,
        )]):
            session.start('hi')
        self.assertAlmostEqual(session.total_input_cost, 1.0)
        self.assertAlmostEqual(session.total_output_cost, 1.0)
        self.assertAlmostEqual(session.total_cost, 2.0)

    def test_cost_accumulates_across_rounds(self):
        session = self.env['muk_ai.session'].create({'name': 'cost-cum', 'agent_id': False})
        with self._patch_provider([self._payload(
            input_tokens=1_000_000, output_tokens=500_000,
        )]):
            session.start('first')
        first_total = session.total_cost
        with self._patch_provider([self._payload(
            input_tokens=2_000_000, output_tokens=100_000,
        )]):
            session.send_message('again')
        self.assertGreater(session.total_cost, first_total)
        self.assertAlmostEqual(session.total_cost - first_total, 2.2)

    def test_cost_stays_zero_when_no_default_model(self):
        self.provider.default_model_id = False
        self.model.active = False
        session = self.env['muk_ai.session'].create({'name': 'no-price', 'agent_id': False})
        with self._patch_provider([self._payload()]):
            session.start('hi')
        self.assertEqual(session.total_cost, 0.0)

    def test_snapshot_exposes_cost(self):
        session = self.env['muk_ai.session'].create({'name': 'snap'})
        session.total_cost = 1.23
        session.total_input_cost = 0.80
        session.total_output_cost = 0.43
        snapshot = session.get_snapshot()
        self.assertAlmostEqual(snapshot['total_cost'], 1.23)
        self.assertAlmostEqual(snapshot['total_input_cost'], 0.80)
        self.assertAlmostEqual(snapshot['total_output_cost'], 0.43)
