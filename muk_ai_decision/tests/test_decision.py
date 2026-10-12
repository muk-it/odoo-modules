from __future__ import annotations

import json
from datetime import timedelta

import requests

from odoo.exceptions import UserError

from odoo.addons.muk_ai_automation.tests.common import text_payload
from odoo.addons.muk_ai_decision.tests.common import DecisionTestCommon, json_response

STATE = 'My invoice shows a double charge from last month.'

QUESTIONS = {
    'team': {
        'type': 'choice',
        'instructions': 'Which team should handle this?',
        'criteria': {'billing': 'Payments and invoices', 'technical': None},
    },
    'anger': {
        'type': 'score',
        'instructions': 'How upset is the customer?',
        'criteria': ['Calm', 'Annoyed', 'Furious'],
    },
    'refund': {
        'type': 'noul',
        'instructions': 'Is the customer asking for a refund?',
        'criteria': {'true': 'Wants money back', 'false': 'No refund'},
    },
}

SYSTEM_ONE = {
    'model': 'jev-1.13.0',
    'answers': {
        'refund': {'type': 'noul', 'noul': 0.9},
        'team': {
            'type': 'choice',
            'choice': 'billing',
            'probabilities': {'billing': 0.9, 'technical': 0.1},
            'confidence': 0.8,
        },
        'anger': {
            'type': 'score',
            'score': 1.1,
            'legend': {'0': 'Calm', '1': 'Annoyed', '2': 'Furious'},
            'probabilities': {'0': 0.0, '1': 0.9, '2': 0.1},
            'confidence': 0.9,
        },
    },
    'usage': {'input_tokens': 300, 'output_tokens': 30},
}

LLM_ANSWER = {
    'team': {'choice': 'billing', 'confidence': 0.7},
    'anger': {'level': 7, 'confidence': 1.4},
    'refund': {'probability': 0.2},
}


def busy_response() -> requests.Response:
    """Build a rate-limit answer naming its retry time as an HTTP date."""
    response = json_response({'error': 'busy'}, 429)
    response.headers['Retry-After'] = 'Wed, 21 Oct 2026 07:28:00 GMT'
    return response


def html_response() -> requests.Response:
    """Build the HTML page a proxy answers in place of the decision API."""
    response = requests.Response()
    response.status_code = 200
    response._content = b'<html>Bad Gateway</html>'
    return response


class TestDecision(DecisionTestCommon):
    """Answer typed questions through the decision service and its MCP tool."""

    @classmethod
    def setUpClass(cls) -> None:
        """Activate the hosted TypeSafe account with a key, on an empty log."""
        super().setUpClass()
        cls.typesafe = cls.env.ref('muk_ai_decision.provider_typesafe')
        cls.typesafe.write({'api_key': 'test-key', 'active': True})
        cls.env['muk_ai.decision.log'].search([]).unlink()
        cls.jev = cls.env.ref('muk_ai_decision.model_jev')

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    def _decide(self, state=STATE, questions=None, **kwargs) -> dict:
        """Run the decision service with the shared questions by default."""
        return self.env['muk_ai.decision']._decide(
            state, QUESTIONS if questions is None else questions, **kwargs
        )

    def _logs(self) -> list:
        """Return the decision logs, oldest first."""
        return self.env['muk_ai.decision.log'].search([], order='id')

    # ----------------------------------------------------------
    # Tests
    # ----------------------------------------------------------

    def test_system_one_answers_are_flagged_priced_and_logged(self):
        partner = self.env['res.partner'].create({'name': 'Customer'})
        with self._capture_post(busy_response(), json_response(SYSTEM_ONE)) as posts:
            result = self._decide(min_confidence=0.85, record=partner, origin='mail')
        _busy, (url, request) = posts
        self.assertEqual(url, 'https://api.typesafe.ai/v1/systemone')
        self.assertEqual(request['headers']['Authorization'], 'Bearer test-key')
        self.assertEqual(
            request['json'],
            {'model': 'jev-latest', 'state': STATE, 'questions': QUESTIONS},
        )
        self.assertEqual(result['model'], 'jev-1.13.0')
        self.assertEqual(
            {key: answer['confident'] for key, answer in result['answers'].items()},
            {'team': False, 'anger': True, 'refund': True},
        )
        log = self._logs()
        self.assertEqual(result['log_id'], log.id)
        self.assertRecordValues(
            log,
            [
                {
                    'model_id': self.jev.id,
                    'served_model': 'jev-1.13.0',
                    'origin': 'mail',
                    'res_model': 'res.partner',
                    'res_id': partner.id,
                    'confident': False,
                    'input_tokens': 300,
                    'output_tokens': 30,
                    'total_cost': 300 * 0.042 / 1_000_000,
                    'currency': 'USD',
                    'state_payload': STATE,
                    'error': False,
                }
            ],
        )
        self.assertEqual(log.answers, result['answers'])

    def test_a_failing_model_hands_over_to_the_next_provider(self):
        bad = {**LLM_ANSWER, 'team': {'choice': 'sales', 'confidence': 1.0}}
        with (
            self._capture_post(json_response({'error': 'overloaded'}, 500)),
            self._mock_responses(
                [text_payload(json.dumps(bad)), text_payload(json.dumps(LLM_ANSWER))]
            ) as rounds,
        ):
            result = self._decide(min_confidence=0.75)
        self.assertEqual(result['model'], 'claude-haiku-4-5')
        self.assertEqual(
            result['answers'],
            {
                'team': {
                    'type': 'choice',
                    'choice': 'billing',
                    'confidence': 0.7,
                    'confident': False,
                },
                'anger': {
                    'type': 'score',
                    'score': 2.0,
                    'legend': {'0': 'Calm', '1': 'Annoyed', '2': 'Furious'},
                    'confidence': 1.0,
                    'confident': True,
                },
                'refund': {'type': 'noul', 'noul': 0.2, 'confident': True},
            },
        )
        luna, haiku = rounds
        self.assertEqual(
            (luna['model'], haiku['model']), ('gpt-5.6-luna', 'claude-haiku-4-5')
        )
        self.assertEqual(luna['reasoning_effort'], 'low')
        schema = luna['text_schema']['schema']
        self.assertEqual(schema['required'], ['team', 'anger', 'refund'])
        self.assertEqual(
            schema['properties']['team']['properties']['choice']['enum'],
            ['billing', 'technical'],
        )
        prompt = luna['inputs'][1]['content']
        self.assertIn(STATE, prompt)
        self.assertIn('level 2: Furious', prompt)
        self.assertIn('true: Wants money back', prompt)
        failed_jev, failed_luna, answered = self._logs()
        self.assertIn('overloaded', failed_jev.error)
        self.assertIn("unknown option 'sales'", failed_luna.error)
        self.assertFalse(answered.error)
        for response, message in (
            (json_response({'error': 'overloaded'}, 500), 'overloaded'),
            (json_response({'model': 'jev-1.13.0'}), 'no answers returned'),
            (html_response(), 'Expecting value'),
            (requests.ConnectionError('connection refused'), 'connection refused'),
        ):
            with (
                self.subTest(message=message),
                self._capture_post(response),
                self.assertRaisesRegex(UserError, message),
            ):
                self._decide(model=self.jev)
        luna = self.env.ref('muk_ai_decision.model_gpt_5_6_luna_decision')
        with (
            self._mock_responses(
                [text_payload(json.dumps(LLM_ANSWER))], repeat_last=True
            ) as rounds,
            self.enter_registry_test_mode(),
        ):
            results = self.env['muk_ai.decision']._decide_batch(
                ['one', 'two', 'three'], QUESTIONS, model=luna
            )
        self.assertEqual(len(rounds), 3)
        self.assertEqual({r['answers']['team']['choice'] for r in results}, {'billing'})

    def test_invalid_questions_and_missing_models_are_refused(self):
        choice = QUESTIONS['team']
        for questions, message in (
            ({}, 'at least one question'),
            ({'q': {'type': 'maybe', 'instructions': 'x'}}, 'type choice, score'),
            ({'q': {'type': 'noul'}}, 'type choice, score'),
            ({'q': {**choice, 'criteria': {'only': None}}}, '2 and 255 options'),
            (
                {'q': {**choice, 'type': 'score', 'criteria': list('abcdefghijk')}},
                '2 and 10 distinct',
            ),
            ({'q': {**choice, 'type': 'score', 'criteria': ['a', 'a']}}, 'distinct'),
            (
                {'q': {'type': 'noul', 'instructions': 'x', 'criteria': {'maybe': 1}}},
                'true and false',
            ),
        ):
            with (
                self.subTest(message=message),
                self._capture_post(),
                self.assertRaisesRegex(UserError, message),
            ):
                self._decide(questions=questions)
        self._clear_default_models('decision')
        with self.assertRaisesRegex(UserError, 'No decision model is available'):
            self._decide()

    def test_the_tool_groups_records_by_answer_with_the_field_values(self):
        self._clear_default_models('decision')
        self.typesafe.default_decision_model_id = self.jev
        tech, retail = self.env['res.partner.industry'].create(
            [{'name': 'Tech'}, {'name': 'Retail'}]
        )
        vip, lead = self.env['res.partner.category'].create(
            [{'name': 'VIP'}, {'name': 'Lead'}]
        )
        ada, bob, cyd = self.env['res.partner'].create(
            [
                {'name': 'Ada', 'comment': 'Runs a software house.'},
                {'name': 'Bob'},
                {'name': 'Cyd'},
            ]
        )
        session = self._session()
        self.assertIn('decide', session._eager_tool_names())
        questions = [
            {
                'field': 'industry_id',
                'candidates': f'[["id", "in", {[tech.id, retail.id]}]]',
            },
            {
                'field': 'category_id',
                'candidates': f'[["id", "in", {[vip.id, lead.id]}]]',
            },
            {'key': 'reseller', 'type': 'noul', 'instructions': 'A reseller?'},
            {'field': 'type', 'instructions': 'Which address is it?'},
        ]

        def answers(industry: float, tags: tuple, reseller: float) -> dict:
            """Build a System One answer for the three questions."""
            return {
                **SYSTEM_ONE,
                'answers': {
                    'industry_id': {
                        'type': 'choice',
                        'choice': 'Tech',
                        'confidence': industry,
                    },
                    f'category_id:{vip.id}': {'type': 'noul', 'noul': tags[0]},
                    f'category_id:{lead.id}': {'type': 'noul', 'noul': tags[1]},
                    'reseller': {'type': 'noul', 'noul': reseller},
                    'type': {
                        'type': 'choice',
                        'choice': 'Invoice Address',
                        'confidence': 0.9,
                    },
                },
            }

        def by_record(request: dict) -> requests.Response:
            """Answer Ada surely, Cyd unsurely, and fail Bob, in any thread order."""
            name = json.loads(request['json']['state'])['Name']
            if name == 'Bob':
                return json_response({'error': 'down'}, 500)
            sure = name == 'Ada'
            return json_response(
                answers(0.9 if sure else 0.4, (0.95, 0.02) if sure else (0.5, 0.1), 0.9)
            )

        def call(**arguments) -> dict:
            """Run the decide tool as an agent dispatches it."""
            text, _info = self.env['muk_mcp.tool']._call(
                'decide', {'questions': questions, **arguments}, self.env
            )
            return json.loads(text)

        with self._capture_post(by_record, by_record, by_record) as posts:
            result = call(
                model='res.partner',
                domain=json.dumps([['id', 'in', [ada.id, bob.id, cyd.id]]]),
                fields=['name', 'comment'],
            )
        sent = posts[0][1]['json']
        self.assertEqual(
            sent['questions']['industry_id']['criteria'], {'Tech': None, 'Retail': None}
        )
        self.assertIn(f'Does "{vip.name}" apply?', str(sent['questions']))
        self.assertEqual(
            {json.loads(post['json']['state'])['Name'] for _url, post in posts},
            {'Ada', 'Bob', 'Cyd'},
        )
        self.assertIn(
            'software house',
            next(
                post['json']['state']
                for _url, post in posts
                if 'Ada' in post['json']['state']
            ),
        )
        self.assertEqual(
            result['groups'],
            {
                'industry_id': {'Tech': {'targets': [ada.id], 'value': tech.id}},
                'category_id': {'VIP': {'targets': [ada.id], 'value': vip.id}},
                'reseller': {'yes': {'targets': [ada.id, cyd.id]}},
                'type': {
                    'Invoice Address': {'targets': [ada.id, cyd.id], 'value': 'invoice'}
                },
            },
        )
        self.assertEqual(
            result['unsure'], {'industry_id': [cyd.id], 'category_id': [cyd.id]}
        )
        self.assertEqual([error['target'] for error in result['errors']], [bob.id])
        with self._capture_post(json_response(answers(0.9, (0.9, 0.9), 0.1))) as posts:
            text = call(
                questions=[questions[0], questions[2]],
                model='res.partner',
                texts=['We build software and resell nothing.'],
            )
        self.assertEqual(
            posts[0][1]['json']['state'], 'We build software and resell nothing.'
        )
        self.assertEqual(
            text['groups'],
            {
                'industry_id': {'Tech': {'targets': [0], 'value': tech.id}},
                'reseller': {'no': {'targets': [0]}},
            },
        )
        self.assertFalse(session.total_cost)
        with self._capture_post(json_response(answers(0.9, (0.9, 0.9), 0.1))) as posts:
            session._dispatch_tool_call(
                'decide',
                {
                    'questions': questions[2:3],
                    'model': 'res.partner',
                    'ids': [ada.id],
                    'fields': ['name', 'comment'],
                },
                'c1',
            )
        self.assertIn('software house', posts[0][1]['json']['state'])
        self.assertAlmostEqual(session.total_cost, 300 * 0.042 / 1_000_000, places=6)
        self.assertAlmostEqual(session.turn_cost_spent, session.total_cost, places=6)
        for arguments, message in (
            ({'questions': questions[2:3]}, 'Pass texts, or a model'),
            ({}, 'with a field needs the model'),
            (
                {'model': 'res.partner', 'questions': [{'field': 'name'}]},
                'cannot be decided',
            ),
            (
                {
                    'model': 'res.partner',
                    'questions': [
                        {
                            'field': 'industry_id',
                            'candidates': f'[["id", "=", {tech.id}]]',
                        }
                    ],
                },
                '2 and 50',
            ),
        ):
            with (
                self.subTest(message=message),
                self.assertRaisesRegex(UserError, message),
            ):
                call(**arguments)
        self._clear_default_models('decision')
        self.assertNotIn('decide', session._eager_tool_names())

    def test_old_logs_are_vacuumed_and_the_connection_test_decides(self):
        with self._capture_post(json_response(SYSTEM_ONE), json_response(SYSTEM_ONE)):
            self._decide()
            self._decide()
        old, recent = self._logs()
        self._backdate(old, timedelta(days=31), 'create_date')
        self.env['muk_ai.decision.log']._autovacuum_logs()
        self.assertEqual(self._logs(), recent)
        self.typesafe.api_key = False
        decis = self.env.ref('muk_ai_decision.provider_decis')
        self.assertEqual(
            [self.typesafe._can_serve(), decis._can_serve()], [False, False]
        )
        decis.api_url = 'http://decis.test'
        self.assertTrue(decis._can_serve())
        with self._capture_post(json_response(SYSTEM_ONE)) as posts:
            self.typesafe.action_test_connection()
        self.assertEqual(posts[0][1]['json']['questions']['ok']['type'], 'noul')
        self.assertNotIn('Authorization', posts[0][1]['headers'])
        with (
            self._capture_post(json_response({'error': 'invalid api key'}, 401)),
            self.assertRaisesRegex(UserError, 'invalid api key'),
        ):
            self.typesafe.action_test_connection()
