from __future__ import annotations

from odoo import models
from odoo.exceptions import ValidationError
from odoo.tests import common, tagged
from odoo.tests.common import new_test_user


@tagged('post_install', '-at_install')
class TestMCPAccessMultiCompany(common.TransactionCase):
    """Cover the global allowlist against per-company record domains."""

    # ----------------------------------------------------------
    # Setup
    # ----------------------------------------------------------

    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls.access_model = cls.env['muk_mcp_access.model']
        cls.mixin = cls.env['muk_mcp.mixin']
        cls.partner_model = cls.env.ref('base.model_res_partner')
        cls.company_a = cls.env['res.company'].create({'name': 'MCP Company A'})
        cls.company_b = cls.env['res.company'].create({'name': 'MCP Company B'})
        cls.user = new_test_user(cls.env, login='mcp_multi_company')
        cls.user.write(
            {
                'company_ids': [(6, 0, [cls.company_a.id, cls.company_b.id])],
                'company_id': cls.company_a.id,
            }
        )
        cls.partner_a = cls.env['res.partner'].create(
            {'name': 'MCP_MC_A', 'company_id': cls.company_a.id},
        )
        cls.partner_b = cls.env['res.partner'].create(
            {'name': 'MCP_MC_B', 'company_id': cls.company_b.id},
        )

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    def _allow_partner(self, domain: str | None = None) -> None:
        """Allow ``res.partner`` for reading, optionally with a record domain."""
        self.access_model.create(
            {
                'model_id': self.partner_model.id,
                'allow_read': True,
                'domain': domain,
            }
        )

    def _search_partner_names(self, mixin: models.BaseModel) -> set:
        """Return the ``MCP_MC_*`` partner names visible through the given mixin env."""
        rows = mixin._mcp_search_read(
            'res.partner',
            domain=[('name', 'like', 'MCP_MC_')],
            fields=['name'],
        )
        return {row['name'] for row in rows}

    # ----------------------------------------------------------
    # Tests
    # ----------------------------------------------------------

    def test_allowlist_entries_are_global_not_company_scoped(self):
        self.assertNotIn('company_id', self.access_model._fields)
        self._allow_partner()
        self.assertTrue(
            self.access_model.with_company(self.company_b)._is_model_allowed(
                'res.partner',
            ),
        )

    def test_company_id_in_domain_follows_the_calling_company(self):
        self._allow_partner("[('company_id', '=', company_id)]")
        self.assertEqual(
            self.access_model.with_company(self.company_a)._get_model_domain(
                'res.partner',
            ),
            [('company_id', '=', self.company_a.id)],
        )
        self.assertEqual(
            self.access_model.with_company(self.company_b)._get_model_domain(
                'res.partner',
            ),
            [('company_id', '=', self.company_b.id)],
        )

    def test_company_id_in_domain_follows_the_calling_user(self):
        self._allow_partner("[('company_id', '=', company_id)]")
        self.assertEqual(
            self.access_model.with_user(self.user)._get_model_domain('res.partner'),
            [('company_id', '=', self.company_a.id)],
        )

    def test_company_ids_in_domain_scopes_the_same_entry_per_environment(self):
        self._allow_partner("[('company_id', 'in', company_ids)]")
        self.assertEqual(
            self._search_partner_names(self.mixin.with_company(self.company_a)),
            {'MCP_MC_A'},
        )
        self.assertEqual(
            self._search_partner_names(self.mixin.with_company(self.company_b)),
            {'MCP_MC_B'},
        )
        both = self.mixin.with_context(
            allowed_company_ids=[self.company_a.id, self.company_b.id],
        )
        self.assertEqual(
            self._search_partner_names(both),
            {'MCP_MC_A', 'MCP_MC_B'},
        )

    def test_time_is_advertised_in_help_but_missing_from_the_eval_context(self):
        self.assertIn('"time"', self.access_model._fields['domain'].help)
        self.assertNotIn('time', self.access_model._eval_context())
        with self.assertRaises(ValidationError) as catcher:
            self._allow_partner(
                "[('create_date', '>', time.strftime('%Y-01-01 00:00:00'))]",
            )
        self.assertIn('Invalid record domain for', str(catcher.exception))
