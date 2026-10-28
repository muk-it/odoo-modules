from __future__ import annotations

from contextlib import AbstractContextManager
from unittest.mock import MagicMock, patch

from odoo import fields
from odoo.tests import new_test_user
from odoo.tools import date_utils

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
        cls.provider.default_chat_model_id = cls.model

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

    def test_model_usage_is_priced_by_the_given_record(self):
        image = self._create_model(
            'test-image-model',
            modality='image',
            context_window=0,
            input_rate=0.0,
            output_rate=0.5,
        )
        session = self.env['muk_ai.session'].create(
            {'name': 'image-cost', 'agent_id': False}
        )
        session._accrue_model_usage(image, {'images': 2})
        self.assertEqual(session.total_input_cost, 0.0)
        self.assertAlmostEqual(session.total_output_cost, 1.0)
        self.assertAlmostEqual(session.total_cost, 1.0)
        self.assertAlmostEqual(session.turn_cost_spent, 1.0)

    def test_cost_stays_zero_when_no_default_model(self):
        self._clear_default_models()
        session = self.env['muk_ai.session'].create(
            {'name': 'no-price', 'agent_id': False}
        )
        with self._patch_provider([self._payload()]):
            session.start('hi')
        self.assertEqual(session.total_cost, 0.0)

    def test_a_monthly_budget_stops_the_chat_once_this_month_spent_it(self):
        user = new_test_user(self.env, 'spender', groups='base.group_user')
        other = new_test_user(self.env, 'neighbour', groups='base.group_user')
        last_month = date_utils.subtract(fields.Datetime.now(), months=1)
        mine = 'Your monthly AI budget of 1.00 USD'
        everyone = 'The monthly AI budget of 1.00 USD for all users'
        params = self.env['ir.config_parameter'].sudo()
        for per_user, total, own, spent, owner, blocked in (
            (1.0, 0.0, 0.0, [(user, None)], user, mine),
            (1.0, 0.0, 5.0, [(user, None)], user, None),
            (1.0, 0.0, 0.0, [(user, last_month)], user, None),
            (1.0, 0.0, 0.0, [(other, None)], user, None),
            (0.0, 1.0, 0.0, [(other, None)], user, everyone),
            (1.0, 0.0, 0.0, [(self.env.user, None)], self.env.user, None),
        ):
            with self.subTest(per_user=per_user, total=total, own=own, spent=spent):
                params.set_param('muk_ai.user_monthly_budget', per_user)
                params.set_param('muk_ai.monthly_budget', total)
                user.ai_monthly_budget = own
                usage = self.env['muk_ai.usage']
                usage.search([]).unlink()
                for spender, date in spent:
                    usage.create(
                        {'user_id': spender.id, 'amount': 1.0}
                        | ({'date': date} if date else {})
                    )
                session = (
                    self.env['muk_ai.session']
                    .with_user(owner)
                    .create({'name': 'Budget', 'agent_id': False})
                )
                with self._patch_provider(
                    [self._payload(input_tokens=1_000_000, output_tokens=0)]
                ) as requests:
                    session.start('go')
                self.assertEqual(requests.call_count, 0 if blocked else 1)
                self.assertEqual(session.state, 'error' if blocked else 'done')
                self.assertTrue((session.error_message or '').startswith(blocked or ''))
                self.assertEqual(
                    usage.search([('session_id', '=', session.id)]).mapped('amount'),
                    [] if blocked else [1.0],
                )

    def test_the_usage_of_months_past_the_retention_is_deleted(self):
        now = fields.Datetime.now()
        usage = self.env['muk_ai.usage']
        usage.search([]).unlink()
        user = new_test_user(self.env, 'spender', groups='base.group_user')
        for months in (0, 5, 7):
            usage.create(
                {
                    'user_id': user.id,
                    'amount': months,
                    'date': date_utils.subtract(now, months=months),
                }
            )
        for retention, kept in ((0, [0, 5]), (3, [0])):
            with self.subTest(retention=retention):
                self.env['ir.config_parameter'].sudo().set_param(
                    'muk_ai.usage_retention_months', retention
                )
                usage._gc_usage()
                self.assertEqual(sorted(usage.search([]).mapped('amount')), kept)
