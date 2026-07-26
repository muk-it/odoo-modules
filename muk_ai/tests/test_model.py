from __future__ import annotations

from odoo import models
from odoo.exceptions import ValidationError
from odoo.tools import mute_logger
from odoo.tools.safe_eval import safe_eval

from odoo.addons.muk_ai.tests.common import AITestCommon


class TestAiModel(AITestCommon):
    """Verify AI model configuration and validation constraints."""

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    def _make_model(
        self,
        model_name: str,
        provider: models.BaseModel | None = None,
        in_rate: float = 1.0,
        out_rate: float = 2.0,
        cache_rate: float = 0.1,
        context_window: int = 128000,
    ) -> models.BaseModel:
        """Create a catalog model record with the given rates and window.

        :param provider: Provider to attach the model to; defaults to
            ``self.provider``.
        """
        return self.env['muk_ai.model'].create(
            {
                'name': model_name,
                'provider_id': (provider or self.provider).id,
                'technical_name': model_name,
                'context_window': context_window,
                'input_rate': in_rate,
                'output_rate': out_rate,
                'cache_read_rate': cache_rate,
            }
        )

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

    def test_compute_usage_cost_with_cache_read_tokens(self):
        record = self._make_model(
            'cached',
            in_rate=1.0,
            out_rate=2.0,
            cache_rate=0.1,
        )
        usage = {
            'input_tokens': 1_000_000,
            'cache_read_tokens': 800_000,
            'output_tokens': 100_000,
        }
        cost = record._compute_usage_cost(usage)
        self.assertAlmostEqual(cost['input_cost'], 0.28)
        self.assertAlmostEqual(cost['output_cost'], 0.2)
        self.assertAlmostEqual(cost['total_cost'], 0.48)

    def test_compute_usage_cost_with_cache_write_tokens(self):
        record = self._make_model('writer', in_rate=1.0, out_rate=2.0)
        record.cache_read_rate = 0.1
        record.cache_write_rate = 1.25
        usage = {
            'input_tokens': 1_000_000,
            'cache_read_tokens': 600_000,
            'cache_write_tokens': 200_000,
            'output_tokens': 100_000,
        }
        cost = record._compute_usage_cost(usage)
        self.assertAlmostEqual(cost['input_cost'], 0.2 + 0.06 + 0.25)
        self.assertAlmostEqual(cost['output_cost'], 0.2)
        self.assertAlmostEqual(cost['total_cost'], 0.71)

    def test_compute_usage_cost_zero_on_empty(self):
        empty = self.env['muk_ai.model'].browse([])
        cost = empty._compute_usage_cost({'input_tokens': 999, 'output_tokens': 999})
        self.assertEqual(cost['total_cost'], 0.0)

    def test_provider_default_model_domain_scopes_to_own_models(self):
        mine = self._make_model('test-oai-def')
        theirs = self._make_model(
            'test-anth-def',
            provider=self.provider_anthropic,
        )
        domain = safe_eval(
            self.env['muk_ai.provider']._fields['default_model_id'].domain,
            {'id': self.provider.id},
        )
        selectable = self.env['muk_ai.model'].search(domain)
        self.assertIn(mine, selectable)
        self.assertNotIn(theirs, selectable)

    def test_positive_context_window_required(self):
        with self.assertRaises(ValidationError):
            self._make_model('zero-ctx', context_window=0)

    def test_unique_provider_model_is_scoped_to_the_provider(self):
        mine = self._make_model('shared', provider=self.provider)
        theirs = self._make_model('shared', provider=self.provider_anthropic)
        self.assertEqual(mine.technical_name, theirs.technical_name)
        self.assertEqual(
            self.env['muk_ai.model'].search_count(
                [('technical_name', '=', 'shared')],
            ),
            2,
        )
        with mute_logger('odoo.sql_db'), self.assertRaises(Exception):
            with self.env.cr.savepoint():
                self._make_model('shared', provider=self.provider)
