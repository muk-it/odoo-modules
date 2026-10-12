from __future__ import annotations

import os
import unittest

from odoo.tests import TransactionCase, tagged

QUESTIONS = {
    'team': {
        'type': 'choice',
        'instructions': 'Which team should handle this message?',
        'criteria': {'billing': 'Payments and invoices', 'technical': 'Bugs'},
    },
    'urgency': {
        'type': 'score',
        'instructions': 'How urgent is the message?',
        'criteria': ['Low', 'Normal', 'High'],
    },
    'refund': {'type': 'noul', 'instructions': 'Does the customer want money back?'},
}


@tagged('muk_ai_decision_live', '-standard')
class TestLiveDecision(TransactionCase):
    """Decide against a real System One server named by ``MUK_AI_DECISION_URL``."""

    @classmethod
    def setUpClass(cls) -> None:
        """Point the self-hosted account at the server, or skip without one."""
        if not (url := os.environ.get('MUK_AI_DECISION_URL')):
            msg = 'MUK_AI_DECISION_URL is not set'
            raise unittest.SkipTest(msg)
        super().setUpClass()
        cls.env.ref('muk_ai_decision.provider_decis').write(
            {
                'active': True,
                'api_url': url,
                'api_key': os.environ.get('MUK_AI_DECISION_KEY'),
            }
        )

    def test_a_real_server_answers_every_question_type(self):
        result = self.env['muk_ai.decision']._decide(
            'I was charged twice for invoice 2026/0042, please refund it today!',
            QUESTIONS,
            model=self.env.ref('muk_ai_decision.model_laya'),
            origin='live',
        )
        answers = result['answers']
        self.assertIn(answers['team']['choice'], QUESTIONS['team']['criteria'])
        self.assertAlmostEqual(sum(answers['team']['probabilities'].values()), 1, 2)
        self.assertTrue(0 <= answers['urgency']['score'] <= 2)
        self.assertTrue(0 <= answers['refund']['noul'] <= 1)
        log = self.env['muk_ai.decision.log'].browse(result['log_id'])
        self.assertFalse(log.error)
        self.assertTrue(log.served_model)
