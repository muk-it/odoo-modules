import json
from collections.abc import Callable

import requests

from odoo import Command, models
from odoo.exceptions import ValidationError

from odoo.addons.muk_ai.tests.common import serve_web
from odoo.addons.muk_ai_decision.tests.common import DecisionTestCommon, json_response


def system_one(answers: dict) -> requests.Response:
    """Build a System One response carrying ``answers``."""
    return json_response({'model': 'jev-1.13.0', 'answers': answers, 'usage': {}})


class TestDecisionAutomation(DecisionTestCommon):
    """Read records, and fill, route and flag them with a decision."""

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
            answers = answers_by_name[json.loads(request['json']['state'])['Name']]
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

    def test_the_input_reads_labelled_fields_or_code_and_shows_in_the_preview(self):
        partner = self.partners[0]
        partner.write(
            {
                'category_id': [Command.set((self.vip | self.lead).ids)],
                'industry_id': self.tech.id,
                'comment': f'<p>{"x" * 2000}</p>',
            }
        )
        action = self.env['ir.actions.server'].create(
            {
                'name': 'Read',
                'state': 'ai_decision',
                'model_id': self.env['ir.model']._get_id('res.partner'),
            }
        )
        self.assertLessEqual(
            {'name', 'email'}, set(action.decision_field_ids.mapped('name'))
        )
        action.decision_field_ids = [
            Command.set(
                [
                    self._field(name)
                    for name in ('name', 'category_id', 'industry_id', 'is_company')
                ]
                + [self._field('comment')]
            )
        ]
        state = json.loads(action._decision_states(partner)[0])
        self.assertEqual(
            state,
            {
                'Name': 'Partner 0',
                'Tags': 'VIP, Lead',
                'Industry': 'Tech',
                'Is a Company': False,
                'Notes': 'x' * 1000,
            },
        )
        action.decision_preview_ref = partner
        self.assertEqual(json.loads(action.decision_preview), state)
        partner.message_post(
            body='Please send an offer.',
            message_type='comment',
            subtype_xmlid='mail.mt_comment',
        )
        partner.message_post(
            body='Call them back.',
            message_type='comment',
            subtype_xmlid='mail.mt_note',
        )
        for external, bodies in (
            (False, ['Call them back.', 'Please send an offer.']),
            (True, ['Please send an offer.']),
        ):
            action.write(
                {'decision_message_count': 2, 'decision_message_external': external}
            )
            messages = json.loads(action._decision_states(partner)[0])['Last Messages']
            self.assertEqual([text.split('): ', 1)[1] for text in messages], bodies)
        action.decision_input_source = 'code'
        self.assertEqual(action._decision_states(partner), ['Partner 0'])
        action.decision_input_code = (
            "text = record.name + ' / ' + record.industry_id.name"
        )
        self.assertEqual(action._decision_states(partner), ['Partner 0 / Tech'])
        self.assertEqual(action.decision_preview, 'Partner 0 / Tech')
        for code, kind, message in (
            ('text = record.no_such_field', 'warning', 'no_such_field'),
            ('name = record.name', 'success', 'decided about 0 records'),
        ):
            with self.subTest(code=code):
                action.decision_input_code = code
                result = action.run()
                self.assertEqual(result['params']['type'], kind)
                self.assertIn(message, result['params']['message'])
        self.assertIn('skipped', action.decision_preview)
        with self.assertRaises(ValidationError):
            action.decision_input_code = 'text = ('

    def test_input_code_reads_the_web_and_skips_records_without_new_input(self):
        p0, p1, _p2 = self.partners
        p0.website = 'https://track.test/a'
        p1.website = 'https://track.test/b'
        action = self.env['ir.actions.server'].create(
            {
                'name': 'Track',
                'state': 'ai_decision',
                'model_id': self.env['ir.model']._get_id('res.partner'),
                'agent_record_domain': self._domain_for(self.partners),
                'decision_input_source': 'code',
                'decision_input_code': (
                    "page = web_fetch(record.website, {'X-Api-Key': 'key'})\n"
                    "text = page and record_text(record, ['name']) + '\\n' + page"
                ),
                'decision_question_ids': [
                    Command.create({'name': 'Delivered?', 'kind': 'noul'})
                ],
            }
        )
        answer = system_one(
            {f'q{action.decision_question_ids.id}': {'type': 'noul', 'noul': 0.9}}
        )
        pages = {'https://track.test/a': (302, {'Location': 'https://cdn.test/a'}, b'')}
        for page, runs, message in (
            (b'Delivered', 1, '1 records: 0 written, 0 unsure, 2 skipped'),
            (b'Delivered', 0, '0 records: 0 written, 0 unsure, 3 skipped'),
            (b'In Transit', 1, '1 records: 0 written, 0 unsure, 2 skipped'),
        ):
            pages['https://cdn.test/a'] = (200, {}, page)
            with serve_web(pages) as connections, self._capture_post(answer) as posts:
                result = action.run()
            self.assertEqual(len(posts), runs)
            self.assertIn(message, result['params']['message'])
        self.assertEqual(
            posts[0][1]['json']['state'], '{"Name": "Partner 0"}\nIn Transit'
        )
        self.assertEqual(
            [c['headers'].get('X-Api-Key') for c in connections], ['key', None, 'key']
        )

    def test_decide_with_ai_fills_routes_and_hands_over_the_unsure(self):
        p0, p1, _p2 = self.partners
        p0.category_id = self.lead
        routed = self._code_action("records.write({'ref': 'routed'})")
        checked = self._code_action("records.write({'function': 'check'})")
        sized = self._code_action("records.write({'email': 'large'})")
        action = self.env['ir.actions.server'].create(
            {
                'name': 'Classify',
                'state': 'ai_decision',
                'model_id': self.env['ir.model']._get_id('res.partner'),
                'agent_record_domain': self._domain_for(self.partners),
                'decision_message_count': 2,
                'decision_question_ids': [
                    Command.create(
                        {
                            'field_id': self._field('industry_id'),
                            'unsure_action_id': checked.id,
                            'candidate_domain': f"[('id', 'in', {[self.tech.id, self.retail.id]})]",
                        }
                    ),
                    Command.create(
                        {
                            'field_id': self._field('category_id'),
                            'tag_operation': 'set',
                            'candidate_domain': f"[('id', 'in', {[self.vip.id, self.lead.id]})]",
                        }
                    ),
                    Command.create({'field_id': self._field('is_company')}),
                    Command.create(
                        {'field_id': self._field('type'), 'field_scale': True}
                    ),
                    Command.create(
                        {
                            'name': 'Which size is the business?',
                            'kind': 'choice',
                            'option_ids': [
                                Command.create(
                                    {'name': 'small', 'description': 'up to 50 people'}
                                ),
                                Command.create(
                                    {'name': 'large', 'action_id': sized.id}
                                ),
                            ],
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
        industry = action.decision_question_ids[0]
        self.assertEqual(industry.candidate_names, 'Retail, Tech')
        industry.candidate_domain = "[('id', '=', 0)]"
        self.assertIn('between 2 and 50', industry.candidate_names)
        industry.candidate_domain = f"[('id', 'in', {[self.tech.id, self.retail.id]})]"
        size, reseller = (f'q{q.id}' for q in action.decision_question_ids[-2:])
        reseller_question = action.decision_question_ids[-1]
        self.assertEqual(reseller_question.route_noul, 'yes')
        reseller_question.route_noul = 'no'
        self.assertEqual(reseller_question.route_answer, 'no')
        reseller_question.route_noul = 'yes'
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
        respond = self._answer(script)
        with self._capture_post(respond, respond, respond) as posts:
            result = action.run()
        self.assertEqual(len(posts), 3)
        sent = {
            json.loads(post['json']['state'])['Name']: post['json']
            for _url, post in posts
        }
        self.assertIn('400 licences', sent['Partner 0']['state'])
        self.assertEqual(
            sent['Partner 0']['questions'][size]['criteria'],
            {'small': 'up to 50 people', 'large': None},
        )
        self.assertIn('3 records: 2 written', result['params']['message'])
        self.assertEqual(p0.industry_id, self.tech)
        self.assertEqual(p0.category_id, self.vip)
        self.assertEqual((p0.is_company, p0.type), (True, 'invoice'))
        self.assertEqual(
            (p1.industry_id, p1.category_id), (self.tech.browse(), self.lead.browse())
        )
        self.assertTrue(p1.is_company)
        self.assertEqual(self.partners.mapped('ref'), ['routed', False, False])
        self.assertEqual(self.partners.mapped('function'), [False, 'check', 'check'])
        self.assertEqual(self.partners.mapped('email'), ['large', 'large', False])
        log = self.env['muk_ai.decision.log'].search(
            [('action_id', '=', action.id), ('res_id', '=', p0.id)]
        )
        self.assertEqual(
            log.applied,
            {
                'industry_id': 'Tech',
                'category_id': {'add': ['VIP'], 'remove': ['Lead']},
                'is_company': 'yes',
                'type': 'Invoice Address',
            },
        )
        self.assertEqual(action.decision_log_count, 3)
        self.assertEqual(
            action.action_open_decision_logs()['domain'],
            [('action_id', '=', action.id)],
        )
        action.agent_record_domain = "[('id', '=', 0)]"
        self.assertFalse(action.run())
        for values, message in (
            ({'name': 'Spam?', 'kind': 'noul', 'route_answer': 'maybe'}, 'yes, no'),
            ({'kind': 'noul'}, 'needs a text'),
            ({'kind': 'field', 'name': 'Topics?'}, 'needs one'),
            (
                {
                    'name': 'Size?',
                    'kind': 'choice',
                    'option_ids': [Command.create({'name': 'one'})],
                },
                '2 and 255 options',
            ),
            (
                {
                    'name': 'Urgency?',
                    'kind': 'score',
                    'option_ids': [
                        Command.create({'name': f'L{n}'}) for n in range(11)
                    ],
                },
                '2 and 10 distinct levels',
            ),
        ):
            with (
                self.subTest(message=message),
                self.assertRaisesRegex(ValidationError, message),
                self.env.cr.savepoint(),
            ):
                action.decision_question_ids = [Command.create(values)]
        action.agent_record_domain = self._domain_for(self.partners)
        self.env.ref('muk_ai_decision.provider_typesafe').api_key = False
        result = action.run()
        self.assertEqual(result['params']['type'], 'warning')
        self.assertIn('No decision model', result['params']['message'])
        self.assertEqual(self.partners.mapped('function'), ['check'] * 3)
