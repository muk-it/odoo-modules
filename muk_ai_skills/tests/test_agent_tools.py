from __future__ import annotations

from odoo.tests.common import TransactionCase, tagged


@tagged('post_install', '-at_install', 'muk_ai_skills', 'tools')
class TestAgentSkillTools(TransactionCase):
    """Test that the skill tools are essential for every agent."""

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
    # Tests
    # ----------------------------------------------------------

    def test_default_essential_names_extend_the_core_set(self):
        names = self.Agent._get_default_essential_tool_names()
        self.assertIn('invoke_skill', names)
        self.assertIn('read_resource', names)
        self.assertIn('search_read', names)

    def test_skill_tools_are_loaded_upfront_on_a_default_agent(self):
        session = self.Session.create(
            {
                'name': 'Essential Tools Session',
                'agent_id': self.agent.id,
            }
        )
        loaded = session._loaded_tool_names()
        self.assertIn('invoke_skill', loaded)
        self.assertIn('read_resource', loaded)

    def test_configured_essential_names_replace_the_skill_tools(self):
        agent = self.Agent.create(
            {
                'name': 'Curated Tools Agent',
                'essential_tool_names': ['search_read'],
            }
        )
        self.assertNotIn('invoke_skill', agent._get_essential_tool_names())
