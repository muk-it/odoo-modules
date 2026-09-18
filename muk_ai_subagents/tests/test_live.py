from __future__ import annotations

import json

from odoo import models
from odoo.tests import TransactionCase, tagged

CHAT_MODEL = 'gpt-5.4-mini'


@tagged('-at_install', 'post_install', '-standard', 'muk_ai_live')
class TestLiveDelegation(TransactionCase):
    """A real model choosing to delegate, and real subagents reporting back.

    Excluded from the standard suite: this costs money, needs the network
    and cannot be deterministic. It is the only test that proves the model
    reads the delegate tool description and actually uses it, rather than
    the runtime handling a payload the test wrote itself.
    """

    # ----------------------------------------------------------
    # Setup
    # ----------------------------------------------------------

    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls.provider = cls.env.ref('muk_ai.provider_openai')
        if not cls.provider.sudo().api_key:
            cls.skipTest(cls, 'No OpenAI key configured on this database')
        cls.provider.sudo().rate_limit = 0
        cls.model = cls.env['muk_ai.model'].search(
            [
                ('provider_id', '=', cls.provider.id),
                ('technical_name', '=', CHAT_MODEL),
            ],
            limit=1,
        )
        cls.worker = cls.env['muk_ai.agent'].create(
            {
                'name': 'Live researcher',
                'model_id': cls.model.id,
                'system_prompt': (
                    'You answer the one question you are given, in a single '
                    'short sentence. You have no tools; answer from what you '
                    'know.'
                ),
            }
        )
        cls.lead = cls.env['muk_ai.agent'].create(
            {
                'name': 'Live lead',
                'model_id': cls.model.id,
                'system_prompt': (
                    'You coordinate. When a request contains several '
                    'independent questions, delegate one task per question to '
                    'Live researcher in a single delegate call, then write '
                    'the final answer yourself from what they report.'
                ),
                'allow_delegation': True,
                'delegate_agent_ids': [(6, 0, cls.worker.ids)],
            }
        )

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    def _calls(self, session: models.Model, name: str) -> list:
        """Return the calls the model actually made to one tool."""
        return [
            entry
            for entry in session.conversation or []
            if entry.get('type') == 'function_call' and entry.get('name') == name
        ]

    # ----------------------------------------------------------
    # Tests
    # ----------------------------------------------------------

    def test_a_real_model_delegates_and_synthesises_what_came_back(self):
        session = self.env['muk_ai.session'].create(
            {'name': 'live run', 'agent_id': self.lead.id}
        )
        session.start(
            'Two separate questions: what is the capital of Austria, and '
            'what is the capital of Portugal? Delegate one question each.'
        )
        self.assertEqual(session.state, 'done', session.error_message or '')
        self.assertTrue(self._calls(session, 'delegate'))

        children = session.child_session_ids.sorted('id')
        self.assertGreaterEqual(len(children), 2)
        self.assertEqual(set(children.mapped('state')), {'done'})
        self.assertTrue(all(children.mapped('last_text')))
        for child in children:
            self.assertEqual(child.parent_session_id, session)
            self.assertEqual(child.user_id, session.user_id)

        # The subagents really answered, and the lead really read them.
        reports = ' '.join(children.mapped('last_text')).lower()
        self.assertIn('vienna', reports)
        self.assertIn('lisbon', reports)
        answer = (session.last_text or '').lower()
        self.assertIn('vienna', answer)
        self.assertIn('lisbon', answer)

        # Every subagent reported exactly once, whatever order they ended in.
        events = self.env['muk_ai.session.event'].search(
            [('session_id', '=', session.id), ('kind', '=', 'delegation_result')]
        )
        self.assertEqual(len(events), len(children))
        self.assertEqual(
            sorted(event.payload['child_id'] for event in events),
            sorted(children.ids),
        )
        for child in children:
            self.assertTrue((child.delegation_brief or {}).get('delivered'))
            self.assertEqual(child.stop_reason, 'done')

        # Real tokens were spent, by the lead and by every subagent.
        self.assertGreater(session.total_input_tokens, 0)
        self.assertGreater(session.total_output_tokens, 0)
        for child in children:
            self.assertGreater(child.total_input_tokens, 0)
            self.assertGreater(child.total_output_tokens, 0)
        self.assertGreaterEqual(session._run_cost(), session.total_cost)

    def test_the_reports_reach_the_model_in_the_order_the_brief_named_them(self):
        session = self.env['muk_ai.session'].create(
            {'name': 'live run', 'agent_id': self.lead.id}
        )
        session.start(
            'Delegate three tasks to Live researcher, in this order: '
            'first the capital of Austria, then the capital of Portugal, '
            'then the capital of Norway. Then list the three answers.'
        )
        self.assertEqual(session.state, 'done', session.error_message or '')
        children = session.child_session_ids.sorted('id')
        self.assertGreaterEqual(len(children), 2)
        outputs = [
            entry
            for entry in session.conversation or []
            if entry.get('type') == 'function_call_output'
        ]
        self.assertTrue(outputs)
        results = json.loads(outputs[0]['output']).get('results') or []
        self.assertEqual(
            [result['child_id'] for result in results], children.ids[: len(results)]
        )
