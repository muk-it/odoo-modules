from odoo.exceptions import ValidationError

from odoo.addons.muk_ai.tests.common import AITestCommon


class TestAiModel(AITestCommon):

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    def _make_model(
        self, model_name, provider=None, in_rate=1.0, out_rate=2.0,
        cache_rate=0.1, context_window=128000,
    ):
        return self.env['muk_ai.model'].create({
            'name': model_name,
            'provider_id': (provider or self.provider).id,
            'technical_name': model_name,
            'context_window': context_window,
            'input_rate': in_rate,
            'output_rate': out_rate,
            'cached_rate': cache_rate,
        })

    # ----------------------------------------------------------
    # Tests
    # ----------------------------------------------------------

    def test_compute_usage_cost_basic(self):
        record = self._make_model('basic', in_rate=1.0, out_rate=2.0)
        usage = {'input_tokens': 1_000_000, 'output_tokens': 500_000}
        cost = record._compute_usage_cost(usage)
        self.assertAlmostEqual(cost['input_cost'], 1.0)
        self.assertAlmostEqual(cost['output_cost'], 1.0)
        self.assertAlmostEqual(cost['total_cost'], 2.0)

    def test_compute_usage_cost_with_cached_tokens(self):
        record = self._make_model(
            'cached', in_rate=1.0, out_rate=2.0, cache_rate=0.1,
        )
        usage = {
            'input_tokens': 1_000_000,
            'cached_tokens': 800_000,
            'output_tokens': 100_000,
        }
        cost = record._compute_usage_cost(usage)
        self.assertAlmostEqual(cost['input_cost'], 0.28)
        self.assertAlmostEqual(cost['output_cost'], 0.2)
        self.assertAlmostEqual(cost['total_cost'], 0.48)

    def test_compute_usage_cost_zero_on_empty(self):
        empty = self.env['muk_ai.model'].browse([])
        cost = empty._compute_usage_cost({'input_tokens': 999, 'output_tokens': 999})
        self.assertEqual(cost['total_cost'], 0.0)

    def test_provider_default_scoped(self):
        openai_default = self._make_model('test-oai-def')
        anthropic_default = self._make_model(
            'test-anth-def', provider=self.provider_anthropic,
        )
        self.provider.default_model_id = openai_default.id
        self.provider_anthropic.default_model_id = anthropic_default.id
        self.assertEqual(self.provider.default_model_id, openai_default)
        self.assertEqual(
            self.provider_anthropic.default_model_id, anthropic_default,
        )

    def test_positive_context_window_required(self):
        with self.assertRaises(ValidationError):
            self._make_model('zero-ctx', context_window=0)

    def test_unique_provider_model(self):
        self._make_model('dup', provider=self.provider)
        with self.assertRaises(Exception):
            self._make_model('dup', provider=self.provider)

    def test_same_model_name_allowed_across_providers(self):
        a = self._make_model('shared', provider=self.provider)
        b = self._make_model('shared', provider=self.provider_anthropic)
        self.assertNotEqual(a.id, b.id)
