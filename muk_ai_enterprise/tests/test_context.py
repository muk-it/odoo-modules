from __future__ import annotations

from odoo import models
from odoo.tests.common import tagged

from .common import BridgeTestCommon


@tagged('post_install', '-at_install', 'muk_ai_enterprise')
class TestContext(BridgeTestCommon):
    """Test EE record context injection into MuK AI sessions."""

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    def _make_session_with_record(self, model: str = 'res.users') -> tuple:
        """Create a record-bound session.

        :param model: the technical name of the model to bind to
        :return: a ``(session, record)`` tuple
        """
        record = self.env[model].search([], limit=1)
        agent = self.env['muk_ai.agent'].create(
            {
                'name': 'Record Context Agent',
                'system_prompt': 'You are a record assistant.',
            }
        )
        session = self.env['muk_ai.session'].create(
            {
                'name': 'Record Session',
                'agent_id': agent.id,
            }
        )
        session.set_view_context(
            {
                'kind': 'record',
                'model': record._name,
                'id': record.id,
            }
        )
        return session, record

    def _make_session(self, name: str) -> models.BaseModel:
        """Create a bare session bound to a throwaway agent.

        :param name: the name used for both the agent and the session
        :return: the created ``muk_ai.session`` record
        """
        agent = self.env['muk_ai.agent'].create({'name': name})
        return self.env['muk_ai.session'].create(
            {
                'name': name,
                'agent_id': agent.id,
            }
        )

    # ----------------------------------------------------------
    # Tests
    # ----------------------------------------------------------

    def test_record_view_context_gets_ee_init_context(self):
        session, record = self._make_session_with_record()
        vc = session.view_context or {}
        self.assertEqual(vc.get('kind'), 'record')
        self.assertEqual(vc.get('model'), record._name)
        self.assertEqual(vc.get('id'), record.id)
        self.assertIn(
            'ee_init_context',
            vc,
            'Bridge must populate ee_init_context for record kind.',
        )
        self.assertIsInstance(vc['ee_init_context'], list)
        self.assertTrue(vc['ee_init_context'])

    def test_non_record_view_context_unchanged(self):
        session = self._make_session('List Agent')
        session.set_view_context(
            {
                'kind': 'list',
                'model': 'res.users',
            }
        )
        vc = session.view_context or {}
        self.assertEqual(vc.get('kind'), 'list')
        self.assertNotIn('ee_init_context', vc)

    def test_unknown_model_view_context_gets_no_ee_block(self):
        session = self._make_session('Bare Model Agent')
        session.set_view_context(
            {
                'kind': 'record',
                'model': 'no.such.model',
                'id': 1,
            }
        )
        vc = session.view_context or {}
        self.assertNotIn('ee_init_context', vc)
        self.assertNotIn(
            '<ee_ctx>',
            session._render_system_prompt(session.agent_id.system_prompt or ''),
        )

    def test_rendered_prompt_contains_ee_context(self):
        session, _record = self._make_session_with_record()
        rendered = session._render_system_prompt(session.agent_id.system_prompt)
        ee = (session.view_context or {}).get('ee_init_context') or []
        self.assertTrue(ee)
        self.assertIn('<ee_ctx>', rendered)
        self.assertIn(ee[0][:30], rendered)
