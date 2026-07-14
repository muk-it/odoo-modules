from __future__ import annotations

from psycopg2 import IntegrityError

from odoo import models
from odoo.exceptions import AccessError
from odoo.tests.common import TransactionCase, new_test_user, tagged
from odoo.tests import Form
from odoo.tools import mute_logger
from odoo.tools.safe_eval import safe_eval


@tagged('post_install', '-at_install', 'muk_ai_skills', 'sharing')
class TestSkillSharing(TransactionCase):
    """Test skill ownership, sharing visibility and record rules."""

    # ----------------------------------------------------------
    # Setup
    # ----------------------------------------------------------

    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls.Skill = cls.env['muk_ai.skill']
        cls.Session = cls.env['muk_ai.session']
        cls.user_owner = new_test_user(cls.env, login='skill_owner')
        cls.user_other = new_test_user(cls.env, login='skill_other')
        cls.user_admin = new_test_user(
            cls.env,
            login='skill_admin',
            groups='base.group_user,base.group_system',
        )

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    def _make_skill(self, user: models.BaseModel, **vals) -> models.BaseModel:
        """Create a skill as the given user, overriding defaults with ``vals``."""
        defaults = {
            'name': 'sharing_skill',
            'description': 'A sharing test skill.',
        }
        defaults.update(vals)
        return self.Skill.with_user(user).create(defaults)

    # ----------------------------------------------------------
    # Tests defaults
    # ----------------------------------------------------------

    def test_new_skill_owned_by_creator(self):
        skill = self._make_skill(self.user_owner)
        self.assertEqual(skill.owner_id, self.user_owner)

    def test_new_skill_private_by_default(self):
        skill = self._make_skill(self.user_owner)
        self.assertEqual(skill.user_ids, self.user_owner)

    def test_create_with_owner_defaults_private_to_owner(self):
        skill = self.Skill.with_user(self.user_admin).create(
            {
                'name': 'owned_elsewhere',
                'description': 'Created by the admin for another owner.',
                'owner_id': self.user_owner.id,
            }
        )
        self.assertEqual(skill.user_ids, self.user_owner)

    def test_owner_change_in_form_moves_default_share(self):
        with Form(self.Skill.with_user(self.user_admin)) as skill_form:
            skill_form.name = 'form_skill'
            skill_form.description = 'Created via the form.'
            skill_form.owner_id = self.user_owner
        skill = self.Skill.search([('name', '=', 'form_skill')])
        self.assertEqual(skill.user_ids, self.user_owner)

    # ----------------------------------------------------------
    # Tests visibility
    # ----------------------------------------------------------

    def test_private_skill_hidden_from_other_user(self):
        skill = self._make_skill(self.user_owner)
        found = self.Skill.with_user(self.user_other).search([('id', '=', skill.id)])
        self.assertFalse(found)

    def test_shared_skill_visible_to_listed_user(self):
        skill = self._make_skill(
            self.user_owner,
            user_ids=[(6, 0, (self.user_owner | self.user_other).ids)],
        )
        found = self.Skill.with_user(self.user_other).search([('id', '=', skill.id)])
        self.assertEqual(found, skill)

    def test_empty_share_list_visible_to_all(self):
        skill = self._make_skill(self.user_owner)
        skill.with_user(self.user_owner).action_share_everyone()
        found = self.Skill.with_user(self.user_other).search([('id', '=', skill.id)])
        self.assertEqual(found, skill)

    def test_make_private_resets_share_list(self):
        skill = self._make_skill(self.user_owner, user_ids=[(5, 0, 0)])
        skill.with_user(self.user_owner).action_make_private()
        self.assertEqual(skill.user_ids, self.user_owner)

    # ----------------------------------------------------------
    # Tests record rules
    # ----------------------------------------------------------

    def test_non_owner_cannot_write(self):
        skill = self._make_skill(self.user_owner, user_ids=[(5, 0, 0)])
        with self.assertRaises(AccessError):
            skill.with_user(self.user_other).write({'label': 'Hijacked'})

    def test_non_owner_cannot_unlink(self):
        skill = self._make_skill(self.user_owner, user_ids=[(5, 0, 0)])
        with self.assertRaises(AccessError):
            skill.with_user(self.user_other).unlink()

    def test_owner_can_write(self):
        skill = self._make_skill(self.user_owner)
        skill.with_user(self.user_owner).write({'label': 'Mine'})
        self.assertEqual(skill.label, 'Mine')

    def test_admin_can_write_any(self):
        skill = self._make_skill(self.user_owner)
        skill.with_user(self.user_admin).write({'label': 'Admin Edit'})
        self.assertEqual(skill.label, 'Admin Edit')

    # ----------------------------------------------------------
    # Tests constraints
    # ----------------------------------------------------------

    def test_read_rule_matches_visibility_domain(self):
        rule = self.env.ref('muk_ai_skills.rule_muk_ai_skill_user_read')
        rule_domain = safe_eval(rule.domain_force, {'user': self.user_owner})
        expected = self.Skill._user_visibility_domain(self.user_owner)
        self.assertEqual(rule_domain, expected)

    def test_user_count_excludes_owner(self):
        skill = self._make_skill(self.user_owner)
        self.assertEqual(skill.user_count, 0)
        skill.with_user(self.user_owner).user_ids = [(4, self.user_other.id)]
        self.assertEqual(skill.user_count, 1)

    def test_is_editable_flags(self):
        skill = self._make_skill(self.user_owner, user_ids=[(5, 0, 0)])
        self.assertTrue(skill.with_user(self.user_owner).is_editable)
        self.assertFalse(skill.with_user(self.user_other).is_editable)
        self.assertTrue(skill.with_user(self.user_admin).is_editable)

    def test_name_unique_per_owner(self):
        self._make_skill(self.user_owner, name='dup_name')
        with self.assertRaises(IntegrityError), mute_logger('odoo.sql_db'):
            with self.env.cr.savepoint():
                self._make_skill(self.user_owner, name='dup_name')

    def test_name_reusable_across_owners(self):
        skill_a = self._make_skill(self.user_owner, name='dup_name')
        skill_b = self._make_skill(self.user_other, name='dup_name')
        self.assertNotEqual(skill_a.owner_id, skill_b.owner_id)

    # ----------------------------------------------------------
    # Tests session visibility
    # ----------------------------------------------------------

    def test_visible_skills_scoped_to_session_user(self):
        own = self._make_skill(self.user_owner, name='own_skill')
        foreign = self._make_skill(self.user_other, name='foreign_skill')
        session = self.Session.with_user(self.user_owner).create(
            {'name': 'Sharing Test Session'}
        )
        visible = session._visible_skills()
        self.assertIn(own, visible)
        self.assertNotIn(foreign, visible)

    def test_visible_skills_dedupe_foreign_ties_deterministic(self):
        first = self._make_skill(
            self.user_owner, name='dup_public', user_ids=[(5, 0, 0)]
        )
        self._make_skill(self.user_other, name='dup_public', user_ids=[(5, 0, 0)])
        third_user = new_test_user(self.env, login='skill_third')
        session = self.Session.with_user(third_user).create(
            {'name': 'Tie Break Session'}
        )
        visible = session._visible_skills().filtered(lambda s: s.name == 'dup_public')
        self.assertEqual(visible, first)

    def test_visible_skills_dedupe_prefers_own(self):
        shared = self._make_skill(
            self.user_other,
            name='dup_skill',
            user_ids=[(5, 0, 0)],
        )
        own = self._make_skill(self.user_owner, name='dup_skill')
        session = self.Session.with_user(self.user_owner).create(
            {'name': 'Dedupe Test Session'}
        )
        visible = session._visible_skills().filtered(lambda s: s.name == 'dup_skill')
        self.assertEqual(visible, own)
        self.assertNotIn(shared, visible)
