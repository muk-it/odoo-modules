from unittest.mock import PropertyMock, patch

from psycopg2 import IntegrityError

from odoo import Command
from odoo.exceptions import AccessError, ValidationError
from odoo.tests import TransactionCase, new_test_user
from odoo.tools import BinaryBytes, mute_logger

from odoo.addons.muk_mcp_skills.models.skill import Skill

VALUES = {
    'name': 'month-end-2',
    'description': 'Close the month.',
    'body': 'Step by step.',
}


class TestSkill(TransactionCase):
    """Keep the skills valid for the clients they are served to."""

    @classmethod
    def setUpClass(cls) -> None:
        """Create a valid skill."""
        super().setUpClass()
        cls.skill = cls.env['muk_mcp_skills.skill'].create(VALUES)

    # ----------------------------------------------------------
    # Tests
    # ----------------------------------------------------------

    def test_texts_the_format_forbids_are_refused(self):
        for field, value in (
            ('name', 'Month'),
            ('name', 'month_end'),
            ('name', '-month'),
            ('name', 'month-'),
            ('name', 'month--end'),
            ('name', 'month end'),
            ('name', 'month\n'),
            ('name', 'm' * 65),
            ('description', 'd' * 1025),
        ):
            with self.subTest(field, value=value[:12]):
                with self.assertRaises(ValidationError):
                    self.skill[field] = value

    @mute_logger('odoo.sql_db')
    def test_a_name_is_taken_once(self):
        with self.assertRaises(IntegrityError):
            self.env['muk_mcp_skills.skill'].create(VALUES)

    def test_files_that_would_hide_each_other_are_refused(self):
        for names in (['SKILL.md'], ['rules.md', 'rules.md']):
            with self.subTest(names):
                with self.assertRaises(ValidationError):
                    self.skill.attachment_ids = [
                        Command.create({'name': name, 'raw': BinaryBytes(b'x')})
                        for name in names
                    ]

    def test_files_larger_than_a_client_accepts_are_refused(self):
        with patch.object(Skill, 'MAX_SIZE', PropertyMock(return_value=200)):
            self.skill.body = 'b' * 50
            with self.assertRaises(ValidationError):
                self.skill.attachment_ids = [
                    Command.create({'name': 'a.txt', 'raw': BinaryBytes(b'a' * 150)})
                ]

    def test_only_administrators_change_skills(self):
        user = new_test_user(self.env, login='skill_user', groups='base.group_user')
        with self.assertRaises(AccessError):
            self.skill.with_user(user).body = 'Mine now.'
