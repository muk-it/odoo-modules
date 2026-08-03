from __future__ import annotations

from odoo import models
from odoo.exceptions import UserError
from odoo.tests.common import TransactionCase, tagged


@tagged('post_install', '-at_install', 'muk_ai_skills', 'model')
class TestSkillModel(TransactionCase):
    """Test the skill model CRUD, name constraints and visibility."""

    # ----------------------------------------------------------
    # Setup
    # ----------------------------------------------------------

    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls.Skill = cls.env['muk_ai.skill']
        cls.Session = cls.env['muk_ai.session']
        cls.Agent = cls.env['muk_ai.agent']
        cls.agent_a = cls.Agent.create({'name': 'Skill Test Agent A'})
        cls.agent_b = cls.Agent.create({'name': 'Skill Test Agent B'})

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    def _make_skill(self, **vals) -> models.BaseModel:
        """Create a skill record, overriding the defaults with ``vals``."""
        defaults = {
            'name': 'demo_skill',
            'description': 'A test skill.',
        }
        defaults.update(vals)
        return self.Skill.create(defaults)

    def _make_session(self, agent: models.BaseModel | None = None) -> models.BaseModel:
        """Create an AI session bound to the given or default agent."""
        return self.Session.create(
            {
                'name': 'Skill Test Session',
                'agent_id': agent.id if agent else self.agent_a.id,
            }
        )

    # ----------------------------------------------------------
    # Tests CRUD
    # ----------------------------------------------------------

    def test_display_name_titles_underscore_name(self):
        skill = self._make_skill(name='my_skill', description='desc')
        self.assertEqual(skill.display_name, 'My Skill')

    def test_display_name_prefers_explicit_label(self):
        skill = self._make_skill(
            name='my_skill',
            label='Custom Label',
            description='d',
        )
        self.assertEqual(skill.display_name, 'Custom Label')

    # ----------------------------------------------------------
    # Tests constraints
    # ----------------------------------------------------------

    def test_name_regex_rejects_uppercase(self):
        with self.assertRaises(UserError):
            self._make_skill(name='BadName', description='d')

    def test_name_regex_rejects_leading_digit(self):
        with self.assertRaises(UserError):
            self._make_skill(name='1skill', description='d')

    def test_name_regex_rejects_dash(self):
        with self.assertRaises(UserError):
            self._make_skill(name='bad-name', description='d')

    # ----------------------------------------------------------
    # Tests visibility
    # ----------------------------------------------------------

    def test_visible_skills_global_only(self):
        global_skill = self._make_skill(name='global', description='g')
        scoped_skill = self._make_skill(
            name='scoped',
            description='s',
            agent_ids=[(6, 0, [self.agent_b.id])],
        )
        session_a = self._make_session(self.agent_a)
        visible = session_a._visible_skills()
        self.assertIn(global_skill, visible)
        self.assertNotIn(scoped_skill, visible)

    def test_visible_skills_scoped_match(self):
        scoped_skill = self._make_skill(
            name='scoped_a',
            description='s',
            agent_ids=[(6, 0, [self.agent_a.id])],
        )
        session_a = self._make_session(self.agent_a)
        self.assertIn(scoped_skill, session_a._visible_skills())

    def test_visible_skills_excludes_inactive(self):
        skill = self._make_skill(name='inactive', description='d')
        skill.active = False
        session = self._make_session(self.agent_a)
        self.assertNotIn(skill, session._visible_skills())
