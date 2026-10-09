from __future__ import annotations

from odoo import models
from odoo.tests import new_test_user

from odoo.addons.muk_ai_chatter.tests.common import ChatterTestCommon


class TestSkillScope(ChatterTestCommon):
    """Test that a linked record stands in for a view a session never had."""

    def _linked(
        self, record: models.BaseModel | None = None, **values: object
    ) -> models.BaseModel:
        """Create a session linked to ``record``, the shared one by default."""
        record = record or self.record
        return self.env['muk_ai.session'].create(
            {'name': 'Linked', 'res_model': record._name, 'res_id': record.id, **values}
        )

    def test_the_linked_record_stands_in_for_a_missing_view(self):
        session = self._linked()
        self.assertEqual(
            session._skill_scope_context(),
            {'kind': 'record', 'model': 'res.partner', 'id': self.record.id},
        )
        skill = self.env['muk_ai.skill'].create(
            {'name': 'linked_scope', 'description': 'Acts on it.', 'scope': 'chatter'}
        )
        session._check_skill_scope(skill)

    def test_a_pinned_view_wins_over_the_linked_record(self):
        session = self._linked()
        session.set_view_context({'kind': 'list', 'model': 'res.partner'})
        self.assertEqual(session._skill_scope_context()['kind'], 'list')

    def test_nothing_stands_in_without_a_readable_record(self):
        hidden = self.env['res.partner'].create({'name': 'Restricted'})
        self._hide(hidden)
        reader = new_test_user(self.env, login='scope_reader')
        for session in (
            self.env['muk_ai.session'].create({'name': 'Bare'}),
            self._linked(hidden, user_id=reader.id),
        ):
            with self.subTest(session=session.name):
                self.assertFalse(session._skill_scope_context())
