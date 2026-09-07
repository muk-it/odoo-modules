from __future__ import annotations

from odoo.exceptions import ValidationError
from odoo.tests.common import TransactionCase, new_test_user, tagged


@tagged('post_install', '-at_install', 'muk_ai_chatter')
class TestQuickAction(TransactionCase):
    """Test saving a prompt typed in the writing helper as a chip of its own."""

    # ----------------------------------------------------------
    # Setup
    # ----------------------------------------------------------

    @classmethod
    def setUpClass(cls) -> None:
        """Expose the skill model the writing helper saves buttons into."""
        super().setUpClass()
        cls.Skill = cls.env['muk_ai.skill']

    # ----------------------------------------------------------
    # Tests
    # ----------------------------------------------------------

    def test_a_saved_prompt_becomes_a_composer_skill(self):
        descriptor = self.Skill.save_composer_prompt(
            'Chase the payment',
            'Ask politely when the invoice will be paid.',
            'generate',
        )
        skill = self.Skill.search([('name', '=', descriptor['name'])])
        self.assertEqual(skill.label, 'Chase the payment')
        self.assertEqual(skill.skill_type, 'composer')
        self.assertEqual(skill.category, 'generate')
        self.assertEqual(skill.body, 'Ask politely when the invoice will be paid.')
        self.assertEqual(skill.owner_id, self.env.user)

    def test_the_technical_name_is_derived_from_the_label(self):
        descriptor = self.Skill.save_composer_prompt(
            'Chase the Payment!', 'Body.', 'generate'
        )
        self.assertEqual(descriptor['name'], 'chase_the_payment')

    def test_a_label_that_cannot_open_a_name_is_prefixed(self):
        descriptor = self.Skill.save_composer_prompt('42 reasons', 'Body.', 'generate')
        self.assertEqual(descriptor['name'], 'prompt_42_reasons')

    def test_a_second_button_of_the_same_name_is_numbered(self):
        first = self.Skill.save_composer_prompt('Follow up', 'Body one.', 'generate')
        second = self.Skill.save_composer_prompt('Follow up', 'Body two.', 'generate')
        self.assertEqual(first['name'], 'follow_up')
        self.assertEqual(second['name'], 'follow_up_2')

    def test_an_archived_button_keeps_its_name_reserved(self):
        first = self.Skill.save_composer_prompt('Follow up', 'Body one.', 'generate')
        self.Skill.search([('name', '=', first['name'])]).action_archive()
        second = self.Skill.save_composer_prompt('Follow up', 'Body two.', 'generate')
        self.assertEqual(second['name'], 'follow_up_2')

    def test_another_user_may_reuse_the_same_name(self):
        mine = self.Skill.save_composer_prompt('Follow up', 'Body.', 'generate')
        other = new_test_user(self.env, login='quick_action_peer')
        theirs = self.Skill.with_user(other).save_composer_prompt(
            'Follow up', 'Body.', 'generate'
        )
        self.assertEqual(mine['name'], theirs['name'])

    def test_a_rewrite_and_a_generate_button_wear_different_icons(self):
        rewrite = self.Skill.save_composer_prompt('Shorten it', 'Body.', 'rewrite')
        generate = self.Skill.save_composer_prompt('Draft it', 'Body.', 'generate')
        self.assertEqual(rewrite['icon'], 'fa-pencil')
        self.assertEqual(generate['icon'], 'fa-magic')

    def test_a_long_prompt_is_summarised_into_the_description(self):
        body = 'x' * 400
        descriptor = self.Skill.save_composer_prompt('Long one', body, 'generate')
        self.assertEqual(len(descriptor['description']), 200)
        self.assertTrue(descriptor['description'].endswith('…'))

    def test_a_button_needs_a_label_and_a_prompt(self):
        with self.assertRaises(ValidationError):
            self.Skill.save_composer_prompt('', 'Body.', 'generate')
        with self.assertRaises(ValidationError):
            self.Skill.save_composer_prompt('Label', '   ', 'generate')

    def test_a_button_needs_a_category_the_helper_offers(self):
        with self.assertRaises(ValidationError):
            self.Skill.save_composer_prompt('Label', 'Body.', 'nonsense')

    def test_the_saved_button_is_private_to_whoever_saved_it(self):
        author = new_test_user(self.env, login='quick_action_author')
        descriptor = self.Skill.with_user(author).save_composer_prompt(
            'Mine only', 'Body.', 'generate'
        )
        skill = self.Skill.search([('name', '=', descriptor['name'])])
        self.assertEqual(skill.owner_id, author)
        self.assertEqual(skill.visibility, 'owner')

    def test_the_panel_lists_the_new_button_straight_away(self):
        descriptor = self.Skill.save_composer_prompt('Fresh chip', 'Body.', 'rewrite')
        offered = self.Skill.fetch_skills('composer')
        self.assertIn(descriptor['name'], [entry['name'] for entry in offered])

    def test_a_label_with_nothing_nameable_still_opens_a_name(self):
        descriptor = self.Skill.save_composer_prompt('!!!', 'Body.', 'generate')
        self.assertEqual(descriptor['name'], 'prompt')
