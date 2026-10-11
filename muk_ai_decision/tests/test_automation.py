import json
from collections.abc import Callable

import requests

from odoo import Command, models
from odoo.exceptions import ValidationError

from odoo.addons.muk_ai.tests.common import json_response
from odoo.addons.muk_ai_automation.tests.common import AutomationTestCommon


def system_one(answers: dict) -> requests.Response:
    """Build a System One response carrying ``answers``."""
    return json_response({'model': 'jev-1.13.0', 'answers': answers, 'usage': {}})


class TestDecisionAutomation(AutomationTestCommon):
    """Gate agent actions on a decision, and fill, route and flag records with one."""

    @classmethod
    def setUpClass(cls) -> None:
        """Answer every decision with TypeSafe and prepare industries and tags."""
        super().setUpClass()
        cls._clear_default_models('decision')
        typesafe = cls.env.ref('muk_ai_decision.provider_typesafe')
        typesafe.write(
            {
                'active': True,
                'api_key': 'test-key',
                'default_decision_model_id': cls.env.ref(
                    'muk_ai_decision.model_jev'
                ).id,
            }
        )
        cls.tech, cls.retail = cls.env['res.partner.industry'].create(
            [{'name': 'Tech'}, {'name': 'Retail'}]
        )
        cls.vip, cls.lead = cls.env['res.partner.category'].create(
            [{'name': 'VIP'}, {'name': 'Lead'}]
        )

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    def _answer(self, answers_by_name: dict) -> Callable:
        """Answer each decision with the answers of the partner named in its state."""

        def answer(request: dict) -> requests.Response:
            """Return the answers for the partner of this request."""
            answers = answers_by_name[json.loads(request['json']['state'])['name']]
            if answers is None:
                return json_response({'error': 'down'}, 500)
            return system_one(answers)

        return answer

    def _code_action(self, code: str) -> models.BaseModel:
        """Create a Python code action on partners."""
        return self.env['ir.actions.server'].create(
            {
                'name': 'Code',
                'state': 'code',
                'model_id': self.env['ir.model']._get_id('res.partner'),
                'code': code,
            }
        )

    def _field(self, name: str) -> int:
        """Return the id of a partner field."""
        return self.env['ir.model.fields']._get('res.partner', name).id

    # ----------------------------------------------------------
    # Tests
    # ----------------------------------------------------------

    def test_the_gate_skips_only_records_confidently_answered_no(self):
        p0, _p1, p2 = self.partners
        for answers, chats in (
            ({'Partner 0': 0.9, 'Partner 1': 0.05, 'Partner 2': 0.5}, p0 | p2),
            ({'Partner 0': 0.1, 'Partner 1': 0.05, 'Partner 2': 0.0}, p0.browse()),
            ({'Partner 0': None, 'Partner 1': 0.0, 'Partner 2': 0.0}, p0),
        ):
            with self.subTest(answers=answers):
                action = self._make_action(
                    agent_dispatch_mode='per_record',
                    agent_gate='Does this contact need a follow-up?',
                )
                gate = self._answer(
                    {
                        name: None
                        if p is None
                        else {'gate': {'type': 'noul', 'noul': p}}
                        for name, p in answers.items()
                    }
                )
                with self._capture_post(gate, gate, gate):
                    result, _sent = self._run(action)
                sessions = self._sessions_of(action)
                self.assertEqual(sessions.mapped('res_id'), chats.ids)
                self.assertEqual(bool(result), bool(chats))
                self.assertEqual(action.decision_log_count, 3)

    def test_decide_with_ai_fills_routes_and_hands_over_the_unsure(self):
        p0, p1, _p2 = self.partners
        p0.category_id = self.lead
        routed = self._code_action("records.write({'ref': 'routed'})")
        checked = self._code_action("records.write({'function': 'check'})")
        action = self.env['ir.actions.server'].create(
            {
                'name': 'Classify',
                'state': 'ai_decision',
                'model_id': self.env['ir.model']._get_id('res.partner'),
                'agent_record_domain': self._domain_for(self.partners),
                'decision_unsure_action_id': checked.id,
                'decision_include_message': True,
                'decision_question_ids': [
                    Command.create(
                        {
                            'field_id': self._field('industry_id'),
                            'candidate_domain': f"[('id', 'in', {[self.tech.id, self.retail.id]})]",
                        }
                    ),
                    Command.create(
                        {
                            'field_id': self._field('category_id'),
                            'candidate_domain': f"[('id', 'in', {[self.vip.id, self.lead.id]})]",
                        }
                    ),
                    Command.create({'field_id': self._field('is_company')}),
                    Command.create({'field_id': self._field('type'), 'kind': 'score'}),
                    Command.create(
                        {
                            'name': 'Which size is the business?',
                            'kind': 'choice',
                            'options': 'small: up to 50 people\nlarge',
                        }
                    ),
                    Command.create(
                        {
                            'name': 'Is this contact a reseller?',
                            'kind': 'noul',
                            'route_answer': 'Yes',
                            'route_action_id': routed.id,
                        }
                    ),
                ],
            }
        )
        size, reseller = (f'q{q.id}' for q in action.decision_question_ids[-2:])
        p0.message_post(body='We resell 400 licences a year.', message_type='comment')

        def answers(industry: float, vip: float) -> dict:
            """Answer all questions surely, the industry and VIP tag as given."""
            return {
                'industry_id': {
                    'type': 'choice',
                    'choice': 'Tech',
                    'confidence': industry,
                },
                f'category_id:{self.vip.id}': {'type': 'noul', 'noul': vip},
                f'category_id:{self.lead.id}': {'type': 'noul', 'noul': 0.01},
                'is_company': {'type': 'noul', 'noul': 0.97},
                'type': {'type': 'score', 'score': 1.2, 'confidence': 0.9},
                size: {'type': 'choice', 'choice': 'large', 'confidence': 0.9},
                reseller: {'type': 'noul', 'noul': 0.9 if industry > 0.5 else 0.1},
            }

        script = {
            'Partner 0': answers(0.9, 0.95),
            'Partner 1': answers(0.3, 0.5),
            'Partner 2': None,
        }
        for shadow in (True, False):
            with self.subTest(shadow=shadow):
                action.decision_shadow = shadow
                respond = self._answer(script)
                with self._capture_post(respond, respond, respond) as posts:
                    result = action.run()
                self.assertEqual(len(posts), 3)
                sent = {
                    json.loads(post['json']['state'])['name']: post['json']
                    for _url, post in posts
                }
                self.assertIn('400 licences', sent['Partner 0']['state'])
                self.assertEqual(
                    sent['Partner 0']['questions'][size]['criteria'],
                    {'small': 'up to 50 people', 'large': None},
                )
                self.assertIn(
                    '3 records: 0 written' if shadow else '3 records: 2 written',
                    result['params']['message'],
                )
                self.assertEqual(
                    p0.industry_id, self.retail.browse() if shadow else self.tech
                )
        self.assertEqual(p0.category_id, self.vip | self.lead)
        self.assertEqual((p0.is_company, p0.type), (True, 'invoice'))
        self.assertEqual(
            (p1.industry_id, p1.category_id), (self.tech.browse(), self.lead.browse())
        )
        self.assertTrue(p1.is_company)
        self.assertEqual(self.partners.mapped('ref'), ['routed', False, False])
        self.assertEqual(self.partners.mapped('function'), [False, 'check', 'check'])
        logs = self.env['muk_ai.decision.log'].search(
            [('action_id', '=', action.id), ('res_id', '=', p0.id)], order='id'
        )
        self.assertEqual(logs.mapped('shadow'), [True, False])
        self.assertEqual(
            logs[-1].applied,
            {
                'industry_id': self.tech.id,
                'category_id': [self.vip.id],
                'is_company': True,
                'type': 'invoice',
            },
        )
        self.assertEqual(action.decision_log_count, 6)
        self.assertEqual(
            action.action_open_decision_logs()['domain'],
            [('action_id', '=', action.id)],
        )
        action.agent_record_domain = "[('id', '=', 0)]"
        self.assertFalse(action.run())
        for values, message in (
            ({'name': 'Spam?', 'kind': 'noul', 'route_answer': 'maybe'}, 'yes, no'),
            ({'kind': 'noul'}, 'needs a text'),
            ({'name': 'Size?', 'kind': 'choice', 'options': 'one'}, 'two options'),
        ):
            with (
                self.subTest(message=message),
                self.assertRaisesRegex(ValidationError, message),
            ):
                action.decision_question_ids = [Command.create(values)]
