from __future__ import annotations

from odoo.tests.common import new_test_user, tagged

from .common import ChatterTestCommon


@tagged('post_install', '-at_install', 'muk_ai_chatter', 'scope')
class TestSkillScopeFallback(ChatterTestCommon):
    """Test that a linked record stands in for a view a session never had."""

    def test_a_session_without_a_view_falls_back_to_its_linked_record(self):
        session = self.env['muk_ai.session'].create(
            {
                'name': 'Linked Session',
                'res_model': self.record._name,
                'res_id': self.record.id,
            }
        )
        self.assertFalse(session.view_context)
        self.assertEqual(
            session._skill_scope_context(),
            {'kind': 'record', 'model': self.record._name, 'id': self.record.id},
        )

    def test_a_record_scoped_skill_runs_for_the_record_it_was_started_from(self):
        skill = self.env['muk_ai.skill'].create(
            {
                'name': 'linked_scope_skill',
                'description': 'Acts on the linked record.',
                'scope': 'chatter',
            }
        )
        session = self.env['muk_ai.session'].create(
            {
                'name': 'Linked Skill Session',
                'res_model': self.record._name,
                'res_id': self.record.id,
            }
        )
        session._check_skill_scope(skill)

    def test_a_pinned_view_still_wins_over_the_linked_record(self):
        session = self.env['muk_ai.session'].create(
            {
                'name': 'Pinned Session',
                'res_model': self.record._name,
                'res_id': self.record.id,
            }
        )
        session.set_view_context({'kind': 'list', 'model': 'sale.order'})
        self.assertEqual(session._skill_scope_context().get('kind'), 'list')

    def test_a_session_with_neither_has_no_scope_context(self):
        session = self.env['muk_ai.session'].create({'name': 'Bare Session'})
        self.assertFalse(session._skill_scope_context())

    def test_a_record_the_owner_cannot_read_does_not_stand_in(self):
        restricted = self.env['res.partner'].create({'name': 'Restricted'})
        reader = new_test_user(
            self.env, login='scope_reader', groups='base.group_public'
        )
        session = self.env['muk_ai.session'].create(
            {
                'name': 'Unreadable Session',
                'user_id': reader.id,
                'res_model': restricted._name,
                'res_id': restricted.id,
            }
        )
        self.assertFalse(session._skill_scope_context())
