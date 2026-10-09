from odoo.exceptions import ValidationError
from odoo.tests import TransactionCase, new_test_user


class TestQuickAction(TransactionCase):
    """Test saving a prompt typed in the writing helper as a chip of its own."""

    def test_a_saved_prompt_becomes_a_private_composer_chip(self):
        Skill = self.env['muk_ai.skill']
        author = new_test_user(self.env, login='quick_action_author')
        descriptor = Skill.with_user(author).save_composer_prompt(
            'Chase the payment', 'Ask when the invoice will be paid.', 'generate'
        )
        skill = Skill.search([('name', '=', descriptor['name'])])
        self.assertEqual(skill.label, 'Chase the payment')
        self.assertEqual(skill.skill_type, 'composer')
        self.assertEqual(skill.category, 'generate')
        self.assertEqual(skill.body, 'Ask when the invoice will be paid.')
        self.assertEqual(skill.owner_id, author)
        self.assertEqual(skill.visibility, 'owner')
        offered = Skill.with_user(author).fetch_skills('composer')
        self.assertIn(skill.name, [row['name'] for row in offered])

    def test_the_name_is_derived_from_the_label_and_kept_unique_per_owner(self):
        Skill = self.env['muk_ai.skill']
        for label, expected in (
            ('Chase the Payment!', 'chase_the_payment'),
            ('42 reasons', 'prompt_42_reasons'),
            ('!!!', 'prompt'),
            ('Follow up', 'follow_up'),
            ('Follow up', 'follow_up_2'),
        ):
            with self.subTest(label=label):
                descriptor = Skill.save_composer_prompt(label, 'Body.', 'generate')
                self.assertEqual(descriptor['name'], expected)
        Skill.search([('name', '=', 'follow_up_2')]).action_archive()
        self.assertEqual(
            Skill.save_composer_prompt('Follow up', 'Body.', 'generate')['name'],
            'follow_up_3',
        )
        peer = new_test_user(self.env, login='quick_action_peer')
        theirs = Skill.with_user(peer).save_composer_prompt('Follow up', 'Body.', 'fix')
        self.assertEqual(theirs['name'], 'follow_up')

    def test_the_chip_wears_its_category_and_a_short_description(self):
        Skill = self.env['muk_ai.skill']
        rewrite = Skill.save_composer_prompt('Shorten it', 'x' * 400, 'rewrite')
        generate = Skill.save_composer_prompt('Draft it', 'Body.', 'generate')
        self.assertEqual((rewrite['icon'], generate['icon']), ('edit', 'wand_stars'))
        self.assertEqual(len(rewrite['description']), 200)
        self.assertTrue(rewrite['description'].endswith('...'))

    def test_an_unusable_chip_is_refused(self):
        for label, body, category in (
            ('', 'Body.', 'generate'),
            ('Label', '   ', 'generate'),
            ('Label', 'Body.', 'nonsense'),
        ):
            with self.subTest(label=label, category=category):
                with self.assertRaises(ValidationError):
                    self.env['muk_ai.skill'].save_composer_prompt(label, body, category)
