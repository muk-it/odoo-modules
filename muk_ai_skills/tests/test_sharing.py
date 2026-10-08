from __future__ import annotations

from psycopg2 import IntegrityError

from odoo import Command, models
from odoo.exceptions import AccessError
from odoo.tests import Form, TransactionCase, new_test_user
from odoo.tools import mute_logger


class TestSkillSharing(TransactionCase):
    """Test who owns, sees and edits a skill and its resources."""

    # ----------------------------------------------------------
    # Setup
    # ----------------------------------------------------------

    @classmethod
    def setUpClass(cls) -> None:
        """Create an owner, another user and an administrator."""
        super().setUpClass()
        cls.Skill = cls.env['muk_ai.skill']
        cls.owner = new_test_user(cls.env, login='skill_owner')
        cls.other = new_test_user(cls.env, login='skill_other')
        cls.admin = new_test_user(
            cls.env, login='skill_admin', groups='base.group_user,base.group_system'
        )

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    def _skill(self, user: models.BaseModel, **values) -> models.BaseModel:
        """Create a skill as ``user``, overriding the defaults with ``values``."""
        return self.Skill.with_user(user).create(
            {'name': 'shared', 'description': 'A sharing test skill.', **values}
        )

    def _shares(self, *users: models.BaseModel) -> list:
        """Return the commands sharing a skill with exactly ``users``."""
        return [Command.set([user.id for user in users])]

    def _sees(self, user: models.BaseModel, skills: models.BaseModel) -> bool:
        """Tell whether ``user`` finds any of ``skills`` in a search."""
        return bool(self.Skill.with_user(user).search([('id', 'in', skills.ids)]))

    def _pending_resource(self, user: models.BaseModel) -> models.BaseModel:
        """Create a resource uploaded on an unsaved skill form."""
        return (
            self.env['ir.attachment']
            .with_user(user)
            .create(
                {
                    'name': 'resource.txt',
                    'res_model': 'muk_ai.skill',
                    'res_id': 0,
                    'raw': b'hello',
                }
            )
        )

    # ----------------------------------------------------------
    # Tests
    # ----------------------------------------------------------

    def test_a_new_skill_is_private_to_its_owner(self):
        skill = self._skill(self.owner)
        self.assertEqual((skill.owner_id, skill.user_ids), (self.owner, self.owner))
        for_owner = self._skill(self.admin, name='for_owner', owner_id=self.owner.id)
        self.assertEqual(for_owner.user_ids, self.owner)
        with Form(self.Skill.with_user(self.admin)) as form:
            form.name = 'from_form'
            form.description = 'Created through the form.'
            form.owner_id = self.owner
        self.assertEqual(form.record.user_ids, self.owner)
        self.assertFalse(self._sees(self.other, skill))

    def test_an_archived_owner_never_makes_a_skill_public_by_accident(self):
        self.owner.active = False
        created_for = self._skill(self.admin, owner_id=self.owner.id)
        self.assertEqual(created_for._unfiltered().user_ids, self.admin)
        authored = self._skill(self.owner, name='authored')
        self.assertEqual(authored.visibility, 'everyone')
        self.assertTrue(self._sees(self.other, authored))

    def test_the_visibility_reads_and_rewrites_the_share_list(self):
        cases = [
            ((self.owner,), 'everyone', (), 'everyone', 0),
            ((self.owner, self.other), 'owner', (self.owner,), 'owner', 0),
            ((), 'users', (self.owner,), 'owner', 0),
            ((self.owner, self.other), 'users', (self.owner, self.other), 'users', 1),
        ]
        for index, (shared, picked, kept, visibility, count) in enumerate(cases):
            with self.subTest(shared=shared, picked=picked):
                skill = self._skill(
                    self.owner, name=f'vis_{index}', user_ids=self._shares(*shared)
                )
                skill.visibility = picked
                skill.invalidate_recordset()
                self.assertEqual(skill.user_ids, self.env['res.users'].union(*kept))
                self.assertEqual(
                    (skill.visibility, skill.user_count), (visibility, count)
                )

    def test_archived_sharees_still_restrict_the_skill(self):
        departed = new_test_user(self.env, login='skill_departed')
        restricted = self._skill(
            self.owner, name='restricted', user_ids=self._shares(self.owner, departed)
        )
        private = self._skill(self.owner, name='private')
        (self.owner | departed).active = False
        (restricted | private).invalidate_recordset()
        self.assertEqual(
            (restricted.visibility, private.visibility), ('users', 'owner')
        )
        self.assertFalse(self._sees(self.other, restricted | private))
        private.visibility = 'everyone'
        self.assertFalse(private._unfiltered().user_ids)
        self.assertTrue(self._sees(self.other, private))

    def test_only_the_owner_or_an_administrator_edits_a_skill(self):
        public = self._skill(self.owner, user_ids=[Command.clear()])
        for operation in ('write', 'unlink'):
            with self.subTest(operation=operation), self.assertRaises(AccessError):
                public.with_user(self.other).check_access(operation)
        public.with_user(self.other).check_access('read')
        public.with_user(self.admin).write({'label': 'Admin Edit'})
        self.assertEqual(public.label, 'Admin Edit')
        self.assertEqual(
            [
                public.with_user(user).is_editable
                for user in (self.owner, self.other, self.admin)
            ],
            [True, False, True],
        )

    def test_a_technical_name_is_unique_per_owner(self):
        self._skill(self.owner, name='dup')
        self._skill(self.other, name='dup')
        with self.assertRaises(IntegrityError), mute_logger('odoo.sql_db'):
            with self.env.cr.savepoint():
                self._skill(self.owner, name='dup')

    def test_resources_uploaded_before_saving_are_bound_to_the_skill(self):
        resource = self._pending_resource(self.owner)
        skill = self._skill(
            self.owner,
            user_ids=self._shares(self.owner, self.other),
            attachment_ids=[Command.set(resource.ids)],
        )
        self.assertEqual(resource.res_id, skill.id)
        resource.with_user(self.other).check_access('read')
        later = self._pending_resource(self.owner)
        skill.with_user(self.owner).write({'attachment_ids': [Command.link(later.id)]})
        self.assertEqual(later.res_id, skill.id)

    def test_a_foreign_resource_cannot_be_linked_into_a_skill(self):
        resource = self._pending_resource(self.owner)
        with self.assertRaises(AccessError):
            self._skill(
                self.other, name='stolen', attachment_ids=[Command.set(resource.ids)]
            )
        skill = self._skill(self.other, name='steal_later')
        with self.assertRaises(AccessError):
            skill.with_user(self.other).write(
                {'attachment_ids': [Command.link(resource.id)]}
            )

    def test_a_surface_is_offered_the_skills_its_user_sees(self):
        self.Skill.search([]).unlink()
        self._skill(self.owner, name='private')
        public = self._skill(self.other, name='public', user_ids=[Command.clear()])
        own = self._skill(
            self.owner,
            name='public',
            label='Mine',
            description='  Does a thing.  ',
            body='Do the thing.',
        )
        offered = self.Skill.with_user(self.other).fetch_skills('chat')
        self.assertEqual([entry['name'] for entry in offered], ['public'])
        self.assertEqual(offered[0]['label'], public.display_name)
        mine = self.Skill.with_user(self.owner).fetch_skills('chat')
        self.assertEqual(sorted(entry['name'] for entry in mine), ['private', 'public'])
        entry = next(entry for entry in mine if entry['name'] == 'public')
        self.assertEqual(
            (entry['label'], entry['description'], entry['body']),
            (own.label, 'Does a thing.', 'Do the thing.'),
        )
        self.assertFalse(self.Skill.with_user(self.owner).fetch_skills('composer'))

    def test_of_two_foreign_skills_with_one_name_the_first_wins(self):
        self.Skill.search([]).unlink()
        first = self._skill(self.owner, name='tie', user_ids=[Command.clear()])
        self._skill(self.other, name='tie', user_ids=[Command.clear()])
        third = new_test_user(self.env, login='skill_third')
        session = self.env['muk_ai.session'].with_user(third).create({'name': 'Tie'})
        self.assertEqual(session._visible_skills(), first)
