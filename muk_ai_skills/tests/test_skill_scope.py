from __future__ import annotations

from odoo import models
from odoo.exceptions import UserError, ValidationError
from odoo.tests.common import TransactionCase, tagged


@tagged('post_install', '-at_install', 'muk_ai_skills', 'scope')
class TestSkillScope(TransactionCase):
    """Test which pinned view contexts make a skill available."""

    # ----------------------------------------------------------
    # Setup
    # ----------------------------------------------------------

    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls.Skill = cls.env['muk_ai.skill']
        cls.Session = cls.env['muk_ai.session']

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    def _make_skill(self, **vals) -> models.BaseModel:
        """Create a skill record, overriding the defaults with ``vals``."""
        defaults = {'name': 'scoped_skill', 'description': 'A scoped skill.'}
        defaults.update(vals)
        return self.Skill.create(defaults)

    def _model(self, name: str) -> models.BaseModel:
        """Return the ``ir.model`` record of the given model name."""
        return self.env['ir.model']._get(name)

    # ----------------------------------------------------------
    # Tests
    # ----------------------------------------------------------

    def test_a_skill_without_a_scope_is_always_available(self):
        skill = self._make_skill()
        self.assertTrue(skill._scope_satisfied_by(None))
        self.assertTrue(skill._scope_satisfied_by({}))
        self.assertTrue(
            skill._scope_satisfied_by(
                {'kind': 'record', 'model': 'res.partner', 'id': 1}
            )
        )

    def test_a_context_skill_takes_a_record_or_a_list(self):
        skill = self._make_skill(scope='context')
        self.assertFalse(skill._scope_satisfied_by(None))
        self.assertTrue(
            skill._scope_satisfied_by(
                {'kind': 'record', 'model': 'res.partner', 'id': 1}
            )
        )
        self.assertTrue(
            skill._scope_satisfied_by({'kind': 'list', 'model': 'res.partner'})
        )
        self.assertTrue(
            skill._scope_satisfied_by({'kind': 'graph', 'model': 'res.partner'})
        )

    def test_a_record_skill_refuses_everything_but_a_record(self):
        skill = self._make_skill(scope='record')
        self.assertTrue(
            skill._scope_satisfied_by(
                {'kind': 'record', 'model': 'res.partner', 'id': 1}
            )
        )
        for kind in ('list', 'pivot', 'graph', 'action'):
            self.assertFalse(
                skill._scope_satisfied_by({'kind': kind, 'model': 'res.partner'}),
                kind,
            )

    def test_an_unsaved_form_is_not_a_record(self):
        skill = self._make_skill(scope='record')
        self.assertFalse(
            skill._scope_satisfied_by(
                {'kind': 'list', 'model': 'res.partner', 'view_type': 'form'}
            )
        )

    def test_a_chatter_skill_needs_a_record_whose_model_has_one(self):
        skill = self._make_skill(scope='chatter')
        self.assertTrue(
            skill._scope_satisfied_by(
                {'kind': 'record', 'model': 'res.partner', 'id': 1}
            )
        )
        self.assertFalse(
            skill._scope_satisfied_by(
                {'kind': 'record', 'model': 'res.currency', 'id': 1}
            )
        )

    def test_a_model_restriction_narrows_any_scope(self):
        skill = self._make_skill(model_ids=[(6, 0, self._model('res.partner').ids)])
        self.assertTrue(
            skill._scope_satisfied_by(
                {'kind': 'record', 'model': 'res.partner', 'id': 1}
            )
        )
        self.assertFalse(
            skill._scope_satisfied_by({'kind': 'record', 'model': 'res.users', 'id': 1})
        )
        self.assertFalse(skill._scope_satisfied_by(None))

    def test_a_chatter_scope_refuses_a_model_without_one(self):
        with self.assertRaises(ValidationError):
            self._make_skill(
                scope='chatter',
                model_ids=[(6, 0, self._model('res.currency').ids)],
            )

    def test_the_requirement_reaches_the_prompt_and_the_panel(self):
        skill = self._make_skill(scope='chatter')
        self.assertIn('chatter', skill._scope_requirement())
        descriptor = skill._skill_descriptor()
        self.assertEqual(descriptor['scope'], 'chatter')
        self.assertEqual(descriptor['models'], [])

    def test_the_panel_descriptor_never_carries_the_body(self):
        self._make_skill(body='Secret instructions.')
        for descriptor in self.Session.available_skill_names():
            self.assertNotIn('body', descriptor)
            self.assertIn('scope', descriptor)

    def test_a_skill_the_context_withholds_is_refused_on_invocation(self):
        skill = self._make_skill(scope='record')
        session = self.Session.create({'name': 'Scope Session'})
        with self.assertRaisesRegex(UserError, 'needs a record open'):
            session.invoke_skill_from_chat(skill.name)

    def test_a_record_context_marks_whether_its_model_has_a_chatter(self):
        session = self.Session.create({'name': 'Enrich Session'})
        session.set_view_context({'kind': 'record', 'model': 'res.partner', 'id': 1})
        self.assertTrue(session.view_context.get('has_chatter'))
        session.set_view_context({'kind': 'record', 'model': 'res.currency', 'id': 1})
        self.assertFalse(session.view_context.get('has_chatter'))

    def test_the_mcp_tool_refuses_what_the_context_withholds(self):
        skill = self._make_skill(scope='record')
        session = self.Session.create({'name': 'MCP Scope Session'})
        mixin = self.env['muk_mcp.mixin'].with_context(muk_mcp_session_id=session.id)
        with self.assertRaisesRegex(UserError, 'needs a record open'):
            mixin._mcp_invoke_skill(skill_name=skill.name)
        session.set_view_context({'kind': 'record', 'model': 'res.partner', 'id': 1})
        self.assertEqual(
            mixin._mcp_invoke_skill(skill_name=skill.name)['name'], skill.name
        )

    def test_a_model_restriction_is_named_in_the_requirement(self):
        skill = self._make_skill(
            scope='record',
            model_ids=[(6, 0, self._model('res.partner').ids)],
        )
        requirement = skill._scope_requirement()
        self.assertIn('needs a record open', requirement)
        self.assertIn('res.partner', requirement)

    def test_the_chatter_constraint_also_guards_a_later_write(self):
        skill = self._make_skill(model_ids=[(6, 0, self._model('res.currency').ids)])
        with self.assertRaises(ValidationError):
            skill.write({'scope': 'chatter'})

    def test_the_prompt_states_what_a_skill_needs_open(self):
        self._make_skill(scope='chatter')
        session = self.Session.create({'name': 'Addendum Session'})
        rendered = session._system_message()['content'][0]['text']
        self.assertIn('needs a record with a chatter open', rendered)

    def test_the_panel_descriptor_carries_the_model_restriction(self):
        self._make_skill(model_ids=[(6, 0, self._model('res.partner').ids)])
        descriptor = next(
            entry
            for entry in self.Session.available_skill_names()
            if entry['name'] == 'scoped_skill'
        )
        self.assertEqual(descriptor['models'], ['res.partner'])
