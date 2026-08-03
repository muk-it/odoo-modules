from __future__ import annotations

from odoo import models
from odoo.tests.common import TransactionCase, tagged


@tagged('post_install', '-at_install', 'muk_ai_skills', 'prompt')
class TestPromptAddendum(TransactionCase):
    """Test the skill addendum injected into the system prompt."""

    # ----------------------------------------------------------
    # Setup
    # ----------------------------------------------------------

    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls.Skill = cls.env['muk_ai.skill']
        cls.Session = cls.env['muk_ai.session']
        cls.Agent = cls.env['muk_ai.agent']
        cls.agent = cls.Agent.create(
            {
                'name': 'Prompt Test Agent',
                'system_prompt': 'You are a helpful assistant.',
            }
        )
        cls.other_agent = cls.Agent.create(
            {
                'name': 'Prompt Test Agent Other',
            }
        )

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    def _make_session(self, agent: models.BaseModel | None = None) -> models.BaseModel:
        """Create an AI session bound to the given or default agent."""
        return self.Session.create(
            {
                'name': 'Prompt Test Session',
                'agent_id': (agent or self.agent).id,
            }
        )

    def _make_skill(self, **vals) -> models.BaseModel:
        """Create a skill record, overriding the defaults with ``vals``."""
        defaults = {
            'name': 'sample_skill',
            'description': 'Sample skill description.',
        }
        defaults.update(vals)
        return self.Skill.create(defaults)

    def _drop_existing_skills(self) -> None:
        """Remove every existing skill to isolate the test fixtures."""
        self.env['muk_ai.skill'].sudo().search([]).unlink()

    # ----------------------------------------------------------
    # Tests
    # ----------------------------------------------------------

    def test_no_skills_no_addendum(self):
        self._drop_existing_skills()
        session = self._make_session()
        rendered = session._system_message()['content'][0]['text']
        self.assertNotIn('<available_skills>', rendered)

    def test_global_skill_appears_in_addendum(self):
        self._drop_existing_skills()
        self._make_skill(name='alpha', description='Do alpha things.')
        session = self._make_session()
        rendered = session._system_message()['content'][0]['text']
        self.assertIn('<available_skills>', rendered)
        self.assertIn('`alpha`', rendered)
        self.assertIn('Do alpha things.', rendered)

    def test_scoped_skill_only_for_matching_agent(self):
        self._drop_existing_skills()
        self._make_skill(
            name='only_other',
            description='Hidden from primary agent.',
            agent_ids=[(6, 0, [self.other_agent.id])],
        )
        session = self._make_session(self.agent)
        rendered = session._system_message()['content'][0]['text']
        self.assertNotIn('only_other', rendered)

    def test_addendum_appended_after_base_prompt(self):
        self._drop_existing_skills()
        self._make_skill(name='beta', description='Beta does beta.')
        session = self._make_session()
        rendered = session._system_message()['content'][0]['text']
        base = 'You are a helpful assistant.'
        self.assertIn(base, rendered)
        self.assertLess(rendered.index(base), rendered.index('<available_skills>'))
