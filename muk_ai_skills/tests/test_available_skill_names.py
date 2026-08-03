from __future__ import annotations

from odoo import models
from odoo.exceptions import AccessError
from odoo.tests.common import TransactionCase, new_test_user, tagged


@tagged('post_install', '-at_install', 'muk_ai_skills', 'discovery')
class TestAvailableSkillNames(TransactionCase):
    """Test the RPC-reachable available_skill_names discovery endpoint."""

    # ----------------------------------------------------------
    # Setup
    # ----------------------------------------------------------

    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls.Skill = cls.env['muk_ai.skill']
        cls.Session = cls.env['muk_ai.session']
        cls.Agent = cls.env['muk_ai.agent']
        cls.agent = cls.Agent.create({'name': 'Discovery Agent'})
        cls.user_a = new_test_user(cls.env, login='skill_discovery_a')
        cls.user_b = new_test_user(cls.env, login='skill_discovery_b')

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    def _make_skill(self, user: models.BaseModel, **vals) -> models.BaseModel:
        """Create a skill owned by ``user``, overriding defaults with ``vals``."""
        defaults = {
            'name': 'discovery_skill',
            'description': 'A discovery test skill.',
        }
        defaults.update(vals)
        return self.Skill.with_user(user).create(defaults)

    def _make_session(self, user: models.BaseModel) -> models.BaseModel:
        """Create an AI session owned by ``user`` and bound to the test agent."""
        return self.Session.with_user(user).create(
            {
                'name': 'Discovery Session',
                'agent_id': self.agent.id,
            }
        )

    def _names_for(self, user: models.BaseModel, session_id: int | None) -> list[str]:
        """Return the skill names ``user`` gets back for ``session_id``."""
        return [
            entry['name']
            for entry in self.Session.with_user(user).available_skill_names(
                session_id=session_id
            )
        ]

    # ----------------------------------------------------------
    # Tests ownership
    # ----------------------------------------------------------

    def test_foreign_session_id_is_refused(self):
        self._make_skill(self.user_a, name='a_private')
        session_a = self._make_session(self.user_a)
        with self.assertRaises(AccessError):
            self.Session.with_user(self.user_b).available_skill_names(
                session_id=session_a.id
            )

    def test_own_session_excludes_another_users_private_skill(self):
        self._make_skill(self.user_a, name='a_private')
        own = self._make_skill(self.user_b, name='b_private')
        session_b = self._make_session(self.user_b)
        names = self._names_for(self.user_b, session_b.id)
        self.assertIn(own.name, names)
        self.assertNotIn('a_private', names)

    def test_unknown_session_id_falls_back_to_the_caller(self):
        own = self._make_skill(self.user_b, name='b_fallback')
        names = self._names_for(self.user_b, 2147483000)
        self.assertIn(own.name, names)

    # ----------------------------------------------------------
    # Tests fallback
    # ----------------------------------------------------------

    def test_without_session_id_lists_the_callers_unscoped_skills(self):
        own = self._make_skill(self.user_b, name='b_unscoped')
        self._make_skill(self.user_a, name='a_unscoped_private')
        names = self._names_for(self.user_b, None)
        self.assertIn(own.name, names)
        self.assertNotIn('a_unscoped_private', names)

    def test_without_session_id_drops_agent_scoped_skills(self):
        self._make_skill(
            self.user_b,
            name='b_scoped',
            agent_ids=[(6, 0, [self.agent.id])],
        )
        self.assertNotIn('b_scoped', self._names_for(self.user_b, None))

    def test_entry_carries_the_icon(self):
        self._make_skill(self.user_b, name='b_iconed', icon='fa-cogs')
        session = self._make_session(self.user_b)
        entries = self.Session.with_user(self.user_b).available_skill_names(
            session_id=session.id
        )
        entry = next(e for e in entries if e['name'] == 'b_iconed')
        self.assertEqual(entry['icon'], 'fa-cogs')

    def test_entry_falls_back_to_the_default_icon(self):
        self._make_skill(self.user_b, name='b_no_icon', icon=False)
        entries = self.Session.with_user(self.user_b).available_skill_names()
        entry = next(e for e in entries if e['name'] == 'b_no_icon')
        self.assertEqual(entry['icon'], 'fa-bolt')

    def test_entry_carries_label_and_stripped_description(self):
        self._make_skill(
            self.user_b,
            name='b_labelled',
            label='Nicely Labelled',
            description='  Does a thing.  ',
        )
        entries = self.Session.with_user(self.user_b).available_skill_names()
        entry = next(e for e in entries if e['name'] == 'b_labelled')
        self.assertEqual(entry['label'], 'Nicely Labelled')
        self.assertEqual(entry['description'], 'Does a thing.')
