from __future__ import annotations

from unittest.mock import patch

from odoo import models
from odoo.tests.common import TransactionCase, tagged


@tagged('post_install', '-at_install', 'muk_ai_skills', 'tools')
class TestAgentSkillTools(TransactionCase):
    """Test that the skill tool is loaded upfront wherever skills are usable."""

    # ----------------------------------------------------------
    # Setup
    # ----------------------------------------------------------

    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls.Agent = cls.env['muk_ai.agent']
        cls.Session = cls.env['muk_ai.session']
        cls.agent = cls.Agent.create({'name': 'Essential Tools Agent'})

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    def _session(self, agent: models.BaseModel) -> models.BaseModel:
        """Create a session bound to ``agent``."""
        return self.Session.create(
            {'name': 'Essential Tools Session', 'agent_id': agent.id}
        )

    def _without_skills(self, session: models.BaseModel):
        """Patch the session so it exposes no skill at all."""
        return patch.object(
            type(session),
            '_visible_skills',
            return_value=self.env['muk_ai.skill'],
        )

    # ----------------------------------------------------------
    # Tests
    # ----------------------------------------------------------

    def test_the_skill_tool_is_loaded_upfront_when_skills_are_visible(self):
        session = self._session(self.agent)
        self.assertTrue(session._visible_skills())
        self.assertIn('invoke_skill', session._eager_tool_names())
        self.assertIn('invoke_skill', session._loaded_tool_names())

    def test_a_session_without_skills_does_not_load_the_skill_tool(self):
        session = self._session(self.agent)
        with self._without_skills(session):
            self.assertNotIn('invoke_skill', session._eager_tool_names())
            self.assertNotIn('invoke_skill', session._loaded_tool_names())

    def test_a_curated_agent_list_no_longer_hides_the_skill_tool(self):
        agent = self.Agent.create(
            {
                'name': 'Curated Tools Agent',
                'essential_tool_names': ['search_read'],
            }
        )
        self.assertNotIn('invoke_skill', agent._get_essential_tool_names())
        self.assertIn('invoke_skill', self._session(agent)._loaded_tool_names())
