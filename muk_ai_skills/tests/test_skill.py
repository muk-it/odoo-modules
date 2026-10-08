from __future__ import annotations

from odoo import Command, models
from odoo.exceptions import ValidationError
from odoo.tests import TransactionCase

RECORD = {'kind': 'record', 'model': 'res.partner', 'id': 1}
CURRENCY = {'kind': 'record', 'model': 'res.currency', 'id': 1}
LIST = {'kind': 'list', 'model': 'res.partner'}
UNSAVED_FORM = {'kind': 'list', 'model': 'res.partner', 'view_type': 'form'}


class TestSkill(TransactionCase):
    """Test the skill record: its technical name, its scope and what it needs open."""

    # ----------------------------------------------------------
    # Setup
    # ----------------------------------------------------------

    @classmethod
    def setUpClass(cls) -> None:
        """Look up a model with a chatter and one without."""
        super().setUpClass()
        cls.partner_model = cls.env['ir.model']._get('res.partner')
        cls.currency_model = cls.env['ir.model']._get('res.currency')

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    def _skill(self, **values) -> models.BaseModel:
        """Create a skill, overriding the defaults with ``values``."""
        return self.env['muk_ai.skill'].create(
            {'name': 'demo', 'description': 'A test skill.', **values}
        )

    # ----------------------------------------------------------
    # Tests
    # ----------------------------------------------------------

    def test_the_technical_name_is_a_lowercase_identifier(self):
        for name in ('BadName', '1skill', 'bad-name'):
            with self.subTest(name=name), self.assertRaises(ValidationError):
                self._skill(name=name)
        self.assertEqual(self._skill(name='my_skill').display_name, 'My Skill')
        self.assertEqual(
            self._skill(name='other', label='Custom').display_name, 'Custom'
        )

    def test_the_scope_decides_what_has_to_be_open(self):
        cases = [
            ('any', None, True),
            ('any', RECORD, True),
            ('context', None, False),
            ('context', LIST, True),
            ('context', RECORD, True),
            ('record', LIST, False),
            ('record', UNSAVED_FORM, False),
            ('record', RECORD, True),
            ('chatter', RECORD, True),
            ('chatter', CURRENCY, False),
        ]
        skills = {
            scope: self._skill(name=f'scope_{scope}', scope=scope)
            for scope in ('any', 'context', 'record', 'chatter')
        }
        for scope, view_context, expected in cases:
            with self.subTest(scope=scope, view_context=view_context):
                self.assertEqual(
                    skills[scope]._scope_satisfied_by(view_context), expected
                )

    def test_a_model_restriction_narrows_the_scope_and_is_named(self):
        skill = self._skill(
            scope='record', model_ids=[Command.set(self.partner_model.ids)]
        )
        self.assertTrue(skill._scope_satisfied_by(RECORD))
        self.assertFalse(skill._scope_satisfied_by({**RECORD, 'model': 'res.users'}))
        self.assertFalse(skill._scope_satisfied_by(None))
        self.assertEqual(
            skill._scope_requirement(), 'needs a record open, only on Contact'
        )

    def test_a_chatter_scope_refuses_a_model_without_a_chatter(self):
        currency = [Command.set(self.currency_model.ids)]
        with self.assertRaises(ValidationError):
            self._skill(scope='chatter', model_ids=currency)
        skill = self._skill(model_ids=currency)
        with self.assertRaises(ValidationError):
            skill.write({'scope': 'chatter'})
