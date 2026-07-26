from __future__ import annotations

import ast

from odoo import models
from odoo.exceptions import AccessError
from odoo.tests.common import TransactionCase, new_test_user, tagged
from odoo.tools import mute_logger


@tagged('post_install', '-at_install')
class TestProductSearch(TransactionCase):
    """Cover the bulk product search wizard domain, preview, and action."""

    # ----------------------------------------------------------
    # Setup
    # ----------------------------------------------------------

    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls.alpha = cls.env['product.template'].create({'name': 'Alpha Widget'})
        cls.beta = cls.env['product.template'].create({'name': 'Beta Widget'})
        cls.gamma = cls.env['product.template'].create({'name': 'Gamma Gizmo'})
        cls.alpha.product_variant_id.default_code = 'REF-ALPHA'
        cls.beta.product_variant_id.default_code = 'REF-BETA'
        cls.gamma.product_variant_id.default_code = 'REF-GAMMA'

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    def make_wizard(self, **vals) -> models.BaseModel:
        """Create a search wizard, defaulting to a newline-split reference match.

        :param vals: field values overriding the defaults
        :return: the created ``muk_product.product_search`` record
        """
        return self.env['muk_product.product_search'].create(
            {
                'value_split_operator': '\n',
                'search_operator': '=',
                'search_field': 'product_variant_ids.default_code',
                **vals,
            }
        )

    def wizard_domain(self, **vals) -> list:
        """Return the domain computed by a wizard created with ``vals``."""
        return ast.literal_eval(self.make_wizard(**vals).search_domain)

    # ----------------------------------------------------------
    # Tests
    # ----------------------------------------------------------

    def test_a_match_search_builds_a_single_in_condition(self):
        self.assertEqual(
            self.wizard_domain(search_value='REF-ALPHA\nREF-BETA'),
            [('product_variant_ids.default_code', 'in', ['REF-ALPHA', 'REF-BETA'])],
        )

    def test_a_contains_search_builds_one_condition_per_value(self):
        self.assertEqual(
            self.wizard_domain(
                search_value='Alpha\nBeta',
                search_operator='ilike',
                search_field='name',
            ),
            ['|', ('name', 'ilike', 'Alpha'), ('name', 'ilike', 'Beta')],
        )

    def test_a_single_contains_value_needs_no_or_operator(self):
        self.assertEqual(
            self.wizard_domain(
                search_value='Alpha',
                search_operator='ilike',
                search_field='name',
            ),
            [('name', 'ilike', 'Alpha')],
        )

    def test_every_split_operator_is_honoured(self):
        for separator in ('\n', ' ', ',', ';', '\t'):
            with self.subTest(separator=separator):
                self.assertEqual(
                    self.wizard_domain(
                        search_value=separator.join(['REF-ALPHA', 'REF-BETA']),
                        value_split_operator=separator,
                    ),
                    [
                        (
                            'product_variant_ids.default_code',
                            'in',
                            ['REF-ALPHA', 'REF-BETA'],
                        )
                    ],
                )

    def test_blank_values_are_dropped_from_a_match_search(self):
        self.assertEqual(
            self.wizard_domain(search_value='REF-ALPHA\n\nREF-BETA\n'),
            [('product_variant_ids.default_code', 'in', ['REF-ALPHA', 'REF-BETA'])],
        )

    def test_surrounding_whitespace_is_stripped_from_every_value(self):
        self.assertEqual(
            self.wizard_domain(search_value='  REF-ALPHA \n\tREF-BETA  '),
            [('product_variant_ids.default_code', 'in', ['REF-ALPHA', 'REF-BETA'])],
        )

    def test_a_trailing_separator_does_not_widen_a_contains_search(self):
        wizard = self.make_wizard(
            search_value='Alpha\n',
            search_operator='ilike',
            search_field='name',
        )
        found = self.env['product.template'].search(
            ast.literal_eval(wizard.search_domain)
        )
        self.assertIn(self.alpha, found)
        self.assertNotIn(self.beta, found)
        self.assertNotIn(self.gamma, found)

    def test_an_empty_search_value_yields_an_empty_domain(self):
        self.assertEqual(self.wizard_domain(search_value=''), [])
        self.assertEqual(self.wizard_domain(search_value='\n\n'), [])
        self.assertEqual(self.wizard_domain(search_value='   '), [])

    def test_the_domain_follows_the_operator_and_field_changes(self):
        wizard = self.make_wizard(search_value='Alpha')
        self.assertEqual(
            ast.literal_eval(wizard.search_domain),
            [('product_variant_ids.default_code', 'in', ['Alpha'])],
        )
        wizard.write({'search_field': 'name', 'search_operator': 'ilike'})
        self.assertEqual(
            ast.literal_eval(wizard.search_domain), [('name', 'ilike', 'Alpha')]
        )

    def test_a_manually_edited_domain_is_used_by_the_action(self):
        wizard = self.make_wizard(search_value='REF-ALPHA')
        wizard.search_domain = repr([('name', '=', 'Gamma Gizmo')])
        found = self.env['product.template'].search(
            wizard.action_search_products()['domain']
        )
        self.assertEqual(found, self.gamma)

    def test_the_action_carries_the_computed_domain(self):
        wizard = self.make_wizard(
            search_value='Alpha\nBeta',
            search_operator='ilike',
            search_field='name',
        )
        action = wizard.action_search_products()
        self.assertEqual(action['res_model'], 'product.template')
        found = self.env['product.template'].search(action['domain'])
        self.assertIn(self.alpha, found)
        self.assertIn(self.beta, found)
        self.assertNotIn(self.gamma, found)

    def test_the_action_of_an_empty_wizard_filters_nothing(self):
        action = self.make_wizard(search_value='').action_search_products()
        self.assertEqual(action['domain'], [])

    def test_the_configured_action_keeps_its_identity_but_loses_its_domain(self):
        target = self.env['ir.actions.act_window'].create(
            {
                'name': 'Only Gamma',
                'res_model': 'product.template',
                'domain': "[('name', '=', 'Gamma Gizmo')]",
            }
        )
        wizard = self.make_wizard(search_value='REF-ALPHA', action_id=target.id)
        action = wizard.action_search_products()
        self.assertEqual(action['name'], 'Only Gamma')
        self.assertEqual(
            action['domain'],
            [('product_variant_ids.default_code', 'in', ['REF-ALPHA'])],
        )

    def test_the_preview_caps_at_seven_records_and_flags_the_overflow(self):
        codes = []
        for index in range(8):
            template = self.env['product.template'].create({'name': f'Bulk {index}'})
            template.product_variant_id.default_code = f'BULK-{index}'
            codes.append(f'BULK-{index}')
        wizard = self.make_wizard(search_value='\n'.join(codes))
        self.assertEqual(len(wizard.product_preview_ids), 7)
        self.assertTrue(wizard.product_preview_hint)

    def test_the_preview_shows_every_match_without_the_overflow_flag(self):
        wizard = self.make_wizard(search_value='REF-ALPHA\nREF-BETA')
        self.assertEqual(wizard.product_preview_ids, self.alpha + self.beta)
        self.assertFalse(wizard.product_preview_hint)

    def test_an_empty_wizard_previews_nothing(self):
        wizard = self.make_wizard(search_value='')
        self.assertFalse(wizard.product_preview_ids)
        self.assertFalse(wizard.product_preview_hint)

    def test_the_preview_handles_a_value_matching_nothing(self):
        wizard = self.make_wizard(search_value='REF-NOTHING')
        self.assertFalse(wizard.product_preview_ids)
        self.assertFalse(wizard.product_preview_hint)

    def test_a_unicode_value_is_matched(self):
        template = self.env['product.template'].create({'name': 'Ünïcodé Prodüct'})
        wizard = self.make_wizard(
            search_value='Ünïcodé',
            search_operator='ilike',
            search_field='name',
        )
        self.assertIn(template, wizard.product_preview_ids)

    def test_a_portal_user_cannot_use_the_wizard(self):
        portal_user = new_test_user(
            self.env,
            login='muk_product_portal',
            groups='base.group_portal',
        )
        with (
            mute_logger(
                'odoo.addons.base.models.ir_model',
                'odoo.addons.base.models.ir_rule',
            ),
            self.assertRaises(AccessError),
        ):
            self.env['muk_product.product_search'].with_user(portal_user).create(
                {'search_value': 'REF-ALPHA'}
            )
