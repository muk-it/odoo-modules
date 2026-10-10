from __future__ import annotations

from odoo.tests import TransactionCase, tagged

CHAT_MODEL = 'gpt-5.4-mini'


@tagged('-standard', 'muk_ai_live')
class TestLiveDelegation(TransactionCase):
    """A real model delegating and synthesising what real subagents reported.

    Excluded from the standard suite: it costs money, needs the network and
    cannot be deterministic. It skips without an OpenAI key.
    """

    # ----------------------------------------------------------
    # Setup
    # ----------------------------------------------------------

    @classmethod
    def setUpClass(cls) -> None:
        """Create a lead and a researcher on a small OpenAI model."""
        super().setUpClass()
        provider = cls.env.ref('muk_ai.provider_openai')
        if not provider.api_key:
            cls.skipTest(cls, 'No OpenAI key configured on this database')
        provider.rate_limit = 0
        model = cls.env['muk_ai.model'].search(
            [('provider_id', '=', provider.id), ('technical_name', '=', CHAT_MODEL)],
            limit=1,
        )
        cls.researcher = cls.env['muk_ai.agent'].create(
            {
                'name': 'Researcher',
                'model_id': model.id,
                'system_prompt': (
                    'You answer the one question you are given, in a single short '
                    'sentence, from what you know.'
                ),
                'tool_filter': ['ask_user'],
            }
        )
        cls.lead = cls.env['muk_ai.agent'].create(
            {
                'name': 'Lead',
                'model_id': model.id,
                'system_prompt': (
                    'You coordinate. When a request holds several independent '
                    'questions, delegate one task per question to Researcher in a '
                    'single delegate call, then answer from what they report.'
                ),
                'allow_delegation': True,
                'delegate_agent_ids': [(6, 0, cls.researcher.ids)],
            }
        )

    # ----------------------------------------------------------
    # Tests
    # ----------------------------------------------------------

    def test_a_real_model_delegates_and_synthesises_what_came_back(self):
        chat = self.env['muk_ai.session'].create(
            {'name': 'live', 'agent_id': self.lead.id}
        )
        chat.start(
            'Two separate questions: what is the capital of Austria, and what is '
            'the capital of Portugal? Delegate one question each.'
        )
        self.assertEqual(chat.state, 'done', chat.error_message or '')
        children = chat.child_session_ids
        self.assertGreaterEqual(len(children), 2)
        self.assertEqual(set(children.mapped('stop_reason')), {'done'})
        reports = ' '.join(children.mapped('last_text')).lower()
        answer = (chat.last_text or '').lower()
        for city in ('vienna', 'lisbon'):
            self.assertIn(city, reports)
            self.assertIn(city, answer)
        self.assertGreater(min(children.mapped('total_output_tokens')), 0)
