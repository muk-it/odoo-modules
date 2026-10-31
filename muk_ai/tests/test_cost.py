from __future__ import annotations

from odoo import fields
from odoo.tests import new_test_user
from odoo.tools import date_utils

from odoo.addons.muk_ai.tests.common import (
    AITestCommon,
    PNG_1x1,
    text_payload,
    tool_payload,
)

M = 1_000_000

IMAGE = {
    'type': 'image',
    'filename': 'generated.png',
    'mimetype': 'image/png',
    'content_base64': PNG_1x1,
}


class TestCost(AITestCommon):
    """Verify what a chat spends is charged to the session, its turn and the limit."""

    # ----------------------------------------------------------
    # Setup
    # ----------------------------------------------------------

    @classmethod
    def setUpClass(cls) -> None:
        """Price the chat and image models and create a plain and a drawing agent."""
        super().setUpClass()
        models = cls.env['muk_ai.model']
        cls.provider.default_chat_model_id = models.create(
            {
                'name': 'Priced',
                'provider_id': cls.provider.id,
                'technical_name': 'gpt-cost',
                'context_window': 10 * M,
                'input_rate': 1.0,
                'output_rate': 2.0,
                'cache_read_rate': 0.5,
                'cache_write_rate': 1.5,
            }
        )
        cls.image, cls.premium = models.create(
            [
                {
                    'name': name,
                    'provider_id': cls.provider.id,
                    'technical_name': name,
                    'modality': 'image',
                    'input_rate': 0.0,
                    'output_rate': rate,
                }
                for name, rate in (
                    ('gpt-cost-image', 0.25),
                    ('gpt-cost-premium', 100.0),
                )
            ]
        )
        cls.agent = cls.env['muk_ai.agent'].create({'name': 'Spender'})
        cls.painter = cls.env['muk_ai.agent'].create(
            {
                'name': 'Painter',
                'enable_image_generation': True,
                'image_model_id': cls.image.id,
            }
        )

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    @staticmethod
    def _limits(request: dict) -> str:
        """Return the turn limit notice a request carries, empty without one."""
        return ''.join(
            block.get('text', '')
            for item in request['inputs']
            for block in item.get('content') or []
            if isinstance(block, dict)
            and str(block.get('text', '')).startswith('<turn_limits>')
        )

    # ----------------------------------------------------------
    # Tests
    # ----------------------------------------------------------

    def test_every_round_is_charged_to_the_session_and_its_turn(self):
        search = ('search_read', {'model': 'res.partner'})
        for payloads, input_cost, output_cost in (
            ([text_payload(usage={'input_tokens': M, 'output_tokens': M // 2})], 1, 1),
            (
                [
                    tool_payload(search, usage={'input_tokens': M // 2}),
                    text_payload(
                        usage={'input_tokens': M // 2, 'output_tokens': M // 4}
                    ),
                ],
                1,
                0.5,
            ),
            (
                [text_payload(usage={'input_tokens': M, 'cache_read_tokens': M})],
                0.5,
                0,
            ),
            (
                [text_payload(usage={'input_tokens': M, 'cache_write_tokens': M // 2})],
                1.25,
                0,
            ),
        ):
            with self.subTest(rounds=len(payloads), input_cost=input_cost):
                session = self._session(agent_id=self.agent.id)
                with self._patch_tool(), self._mock_responses(payloads):
                    snapshot = session.start('go')
                self.assertAlmostEqual(snapshot['total_input_cost'], input_cost)
                self.assertAlmostEqual(snapshot['total_output_cost'], output_cost)
                self.assertAlmostEqual(snapshot['total_cost'], input_cost + output_cost)
                self.assertAlmostEqual(
                    snapshot['turn_usage']['cost'], input_cost + output_cost
                )
        self._clear_default_models()
        session = self._session(agent_id=self.agent.id)
        with self._mock_responses([text_payload(usage={'input_tokens': M})]):
            self.assertEqual(session.start('go')['total_cost'], 0)

    def test_a_new_turn_restarts_the_turn_cost_and_a_resumed_one_keeps_it(self):
        session = self._session(agent_id=self.agent.id)
        with self._mock_responses(
            [
                tool_payload(
                    ('ask_user', {'question': 'Sure?'}), usage={'input_tokens': M}
                ),
                text_payload(usage={'input_tokens': 2 * M}),
            ]
        ):
            session.start('first')
            self.assertEqual(session.state, 'waiting')
            snapshot = session.answer('yes')
        self.assertAlmostEqual(snapshot['turn_usage']['cost'], 3)
        self.assertAlmostEqual(session.turn_cost_spent, 2)
        with self._mock_responses([text_payload(usage={'output_tokens': M})]):
            snapshot = session.send_message('second')
        self.assertAlmostEqual(snapshot['turn_usage']['cost'], 2)
        self.assertAlmostEqual(session.turn_cost_spent, 2)
        self.assertAlmostEqual(snapshot['total_cost'], 5)
        with self._mock_responses(
            [text_payload('summary', usage={'input_tokens': M // 2})]
        ):
            snapshot = session.compact()
        self.assertAlmostEqual(snapshot['total_cost'], 5.5)

    def test_the_turn_cost_limit_warns_then_stops_the_turn(self):
        self.env['res.config.settings'].create({'ai_turn_cost_limit': 1.0}).set_values()
        euro = self._create_model('gpt-cost-eur', currency='EUR', context_window=10 * M)
        session = self._session(
            agent_id=self.env['muk_ai.agent']
            .create({'name': 'Euro', 'model_id': euro.id})
            .id
        )
        search = ('search_read', {'model': 'res.partner'})
        with (
            self._patch_tool(),
            self._mock_responses(
                [
                    tool_payload(search, usage={'input_tokens': M // 2}),
                    tool_payload(search, usage={'input_tokens': M * 3 // 10}),
                    tool_payload(search, usage={'input_tokens': M // 5}),
                    text_payload(),
                ]
            ) as requests,
        ):
            session.start('spend')
        self.assertEqual(len(requests), 3)
        self.assertFalse(self._limits(requests[0]))
        self.assertFalse(self._limits(requests[1]))
        self.assertIn(
            'Only 0.20 EUR of the 1.00 EUR turn cost budget remain.',
            self._limits(requests[2]),
        )
        self.assertEqual(session.state, 'error')
        self.assertIn('Turn cost budget reached (1.00 EUR)', session.error_message)

    def test_a_tool_cost_counts_on_the_chat_and_is_booked_by_the_tool_only(self):
        one = {'model_id': self.image.id, 'usage': {'images': 1}, 'total': 0.25}
        premium = {**one, 'model_id': self.premium.id}
        for name, result, charged in (
            ('generate_image', {**IMAGE, 'cost': one}, 0.25),
            ('generate_image', {**IMAGE, 'cost': {**one, 'usage': {'images': 2}}}, 0.5),
            ('generate_image', {**IMAGE, 'cost': premium}, 100),
            ('web_fetch', {'text': 'page', 'cost': [one, one]}, 0.5),
            ('generate_image', {**IMAGE, 'cost': {'usage': {'images': 1}}}, 0),
            ('generate_image', {**IMAGE, 'cost': {**one, 'model_id': 0}}, 0),
            ('generate_image', {**IMAGE, 'cost': 3}, 0),
            ('generate_image', [{**IMAGE, 'cost': one}], 0),
            ('generate_image', IMAGE, 0),
        ):
            with self.subTest(tool=name, result=result):
                session = self._session(agent_id=self.painter.id)
                with (
                    self._patch_tool({name: result}) as calls,
                    self._mock_responses(
                        [
                            tool_payload((name, {'prompt': 'a dot'}), usage={}),
                            text_payload(usage={}),
                        ]
                    ),
                ):
                    snapshot = session.start('draw')
                self.assertEqual([call['name'] for call in calls], [name])
                self.assertAlmostEqual(snapshot['total_output_cost'], charged)
                self.assertAlmostEqual(snapshot['turn_usage'].get('cost', 0), charged)
                self.assertFalse(
                    self.env['muk_ai.usage'].search([('session_id', '=', session.id)])
                )

    def test_an_image_counts_against_the_turn_cost_limit(self):
        self._set_params({'muk_ai.turn_cost_limit': 0.2})
        session = self._session(agent_id=self.painter.id)
        with (
            self._patch_tool(
                {
                    'generate_image': {
                        **IMAGE,
                        'cost': {'model_id': self.image.id, 'usage': {'images': 1}},
                    }
                }
            ),
            self._mock_responses(
                [
                    tool_payload(('generate_image', {'prompt': 'a dot'}), usage={}),
                    text_payload(usage={}),
                ]
            ) as requests,
        ):
            session.start('draw')
        self.assertEqual(len(requests), 1)
        self.assertEqual(session.state, 'error')
        self.assertIn('Turn cost budget reached (0.20 USD)', session.error_message)

    def test_a_monthly_budget_stops_the_chat_once_this_month_spent_it(self):
        user = new_test_user(self.env, 'spender', groups='base.group_user')
        other = new_test_user(self.env, 'neighbour', groups='base.group_user')
        last_month = date_utils.subtract(fields.Datetime.now(), months=1)
        mine = 'Your monthly AI budget of 1.00 USD'
        everyone = 'The monthly AI budget of 1.00 USD for all users'
        for per_user, total, own, spent, owner, blocked in (
            (1.0, 0.0, 0.0, [(user, None)], user, mine),
            (1.0, 0.0, 5.0, [(user, None)], user, None),
            (1.0, 0.0, 0.0, [(user, last_month)], user, None),
            (1.0, 0.0, 0.0, [(other, None)], user, None),
            (0.0, 1.0, 0.0, [(other, None)], user, everyone),
            (1.0, 0.0, 0.0, [(self.env.user, None)], self.env.user, None),
        ):
            with self.subTest(per_user=per_user, total=total, own=own, spent=spent):
                self._set_params(
                    {
                        'muk_ai.user_monthly_budget': per_user,
                        'muk_ai.monthly_budget': total,
                    }
                )
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
                    .create({'name': 'Budget', 'agent_id': self.agent.id})
                )
                with self._mock_responses(
                    [text_payload(usage={'input_tokens': M})]
                ) as requests:
                    session.start('go')
                self.assertEqual(len(requests), 0 if blocked else 1)
                self.assertEqual(session.state, 'error' if blocked else 'done')
                self.assertTrue((session.error_message or '').startswith(blocked or ''))
                self.assertEqual(
                    usage.search([('session_id', '=', session.id)]).mapped(
                        lambda row: (row.purpose, row.amount)
                    ),
                    [] if blocked else [('chat', 1.0)],
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
                self._set_params({'muk_ai.usage_retention_months': retention})
                usage._gc_usage()
                self.assertEqual(sorted(usage.search([]).mapped('amount')), kept)
