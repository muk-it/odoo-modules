from __future__ import annotations

from odoo.exceptions import AccessError
from odoo.tests import common, tagged


@tagged('post_install', '-at_install')
class TestMCPAccessModel(common.TransactionCase):
    """Test model-level access control and record domains for MCP."""

    # ----------------------------------------------------------
    # Setup
    # ----------------------------------------------------------

    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls.access_model = cls.env['muk_mcp_access.model']
        cls.mixin = cls.env['muk_mcp.mixin']
        cls.partner_model = cls.env.ref('base.model_res_partner')
        cls.user_model = cls.env.ref('base.model_res_users')
        cls.country_model = cls.env.ref('base.model_res_country')

    # ----------------------------------------------------------
    # Tests: allowlist inactive (empty)
    # ----------------------------------------------------------

    def test_empty_allowlist_allows_everything(self):
        self.assertTrue(
            self.access_model._is_model_allowed('res.partner'),
        )
        self.assertTrue(
            self.access_model._is_model_allowed('res.users', 'write'),
        )

    def test_empty_allowlist_returns_none(self):
        self.assertIsNone(self.access_model._get_allowed_model_names())

    def test_resolve_model_passes_with_empty_allowlist(self):
        result = self.mixin._resolve_model('res.partner')
        self.assertEqual(result._name, 'res.partner')

    def test_list_models_unfiltered_with_empty_allowlist(self):
        result = self.mixin._mcp_list_models(search='res.partner')
        names = [m['model'] for m in result]
        self.assertIn('res.partner', names)

    # ----------------------------------------------------------
    # Tests: allowlist active (non-empty)
    # ----------------------------------------------------------

    def test_allowed_model_passes(self):
        self.access_model.create(
            {
                'model_id': self.partner_model.id,
                'allow_read': True,
                'allow_write': False,
            }
        )
        self.assertTrue(
            self.access_model._is_model_allowed('res.partner', 'read'),
        )

    def test_unlisted_model_blocked(self):
        self.access_model.create(
            {
                'model_id': self.partner_model.id,
                'allow_read': True,
            }
        )
        self.assertFalse(
            self.access_model._is_model_allowed('res.users', 'read'),
        )

    def test_write_denied_when_read_only(self):
        self.access_model.create(
            {
                'model_id': self.partner_model.id,
                'allow_read': True,
                'allow_write': False,
            }
        )
        self.assertFalse(
            self.access_model._is_model_allowed('res.partner', 'write'),
        )

    def test_write_allowed_when_enabled(self):
        self.access_model.create(
            {
                'model_id': self.partner_model.id,
                'allow_read': True,
                'allow_write': True,
            }
        )
        self.assertTrue(
            self.access_model._is_model_allowed('res.partner', 'write'),
        )

    def test_resolve_model_blocks_unlisted(self):
        self.access_model.create(
            {
                'model_id': self.partner_model.id,
                'allow_read': True,
            }
        )
        with self.assertRaises(AccessError):
            self.mixin._resolve_model('res.users')

    def test_resolve_model_allows_listed(self):
        self.access_model.create(
            {
                'model_id': self.partner_model.id,
                'allow_read': True,
            }
        )
        result = self.mixin._resolve_model('res.partner')
        self.assertEqual(result._name, 'res.partner')

    def test_list_models_filters_to_allowlist(self):
        self.access_model.create(
            {
                'model_id': self.partner_model.id,
                'allow_read': True,
            }
        )
        result = self.mixin._mcp_list_models(search='res.')
        names = [m['model'] for m in result]
        self.assertIn('res.partner', names)
        for name in names:
            self.assertEqual(name, 'res.partner')

    def test_get_allowed_model_names_read(self):
        self.access_model.create(
            {
                'model_id': self.partner_model.id,
                'allow_read': True,
                'allow_write': False,
            }
        )
        self.access_model.create(
            {
                'model_id': self.user_model.id,
                'allow_read': True,
                'allow_write': True,
            }
        )
        read_models = self.access_model._get_allowed_model_names('read')
        self.assertEqual(read_models, {'res.partner', 'res.users'})

    def test_get_allowed_model_names_write(self):
        self.access_model.create(
            {
                'model_id': self.partner_model.id,
                'allow_read': True,
                'allow_write': False,
            }
        )
        self.access_model.create(
            {
                'model_id': self.user_model.id,
                'allow_read': True,
                'allow_write': True,
            }
        )
        write_models = self.access_model._get_allowed_model_names('write')
        self.assertEqual(write_models, {'res.users'})

    # ----------------------------------------------------------
    # Tests: constraints
    # ----------------------------------------------------------

    def test_duplicate_blocked_by_wizard(self):
        self.access_model.create(
            {
                'model_id': self.partner_model.id,
            }
        )
        wizard = self.env['muk_mcp_access.model.selection'].create(
            {
                'model_ids': [(6, 0, [self.partner_model.id])],
            }
        )
        wizard.action_enable_models()
        self.assertEqual(
            self.access_model.search_count(
                [
                    ('model_id', '=', self.partner_model.id),
                ]
            ),
            1,
        )

    def test_no_permissions_raises(self):
        with self.assertRaises(Exception):
            self.access_model.create(
                {
                    'model_id': self.partner_model.id,
                    'allow_read': False,
                    'allow_write': False,
                }
            )

    # ----------------------------------------------------------
    # Tests: record domain
    # ----------------------------------------------------------

    def test_no_domain_returns_none(self):
        self.access_model.create(
            {
                'model_id': self.partner_model.id,
                'allow_read': True,
            }
        )
        self.assertIsNone(
            self.access_model._get_model_domain('res.partner'),
        )

    def test_domain_returned_when_set(self):
        self.access_model.create(
            {
                'model_id': self.partner_model.id,
                'allow_read': True,
                'domain': "[('is_company', '=', True)]",
            }
        )
        self.assertEqual(
            self.access_model._get_model_domain('res.partner'),
            [('is_company', '=', True)],
        )

    def test_domain_inactive_allowlist_returns_none(self):
        self.assertIsNone(
            self.access_model._get_model_domain('res.partner'),
        )

    def test_invalid_domain_rejected(self):
        with self.assertRaises(Exception):
            self.access_model.create(
                {
                    'model_id': self.partner_model.id,
                    'allow_read': True,
                    'domain': "[('does_not_exist', '=', 1)]",
                }
            )

    def test_search_read_applies_domain(self):
        self.access_model.create(
            {
                'model_id': self.country_model.id,
                'allow_read': True,
                'domain': "[('code', '=', 'BE')]",
            }
        )
        rows = self.mixin._mcp_search_read(
            'res.country',
            domain=[('code', 'in', ['BE', 'FR'])],
            fields=['code'],
        )
        codes = {row['code'] for row in rows}
        self.assertEqual(codes, {'BE'})

    def test_search_count_applies_domain(self):
        self.access_model.create(
            {
                'model_id': self.country_model.id,
                'allow_read': True,
                'domain': "[('code', '=', 'BE')]",
            }
        )
        result = self.mixin._mcp_search_count(
            'res.country',
            domain=[('code', 'in', ['BE', 'FR'])],
        )
        self.assertEqual(result['count'], 1)

    def test_read_records_blocks_out_of_domain(self):
        self.access_model.create(
            {
                'model_id': self.country_model.id,
                'allow_read': True,
                'domain': "[('code', '=', 'BE')]",
            }
        )
        with self.assertRaises(AccessError):
            self.mixin._mcp_read_records(
                'res.country',
                [self.env.ref('base.fr').id],
            )

    def test_read_records_allows_in_domain(self):
        self.access_model.create(
            {
                'model_id': self.country_model.id,
                'allow_read': True,
                'domain': "[('code', '=', 'BE')]",
            }
        )
        rows = self.mixin._mcp_read_records(
            'res.country',
            [self.env.ref('base.be').id],
            fields=['code'],
        )
        self.assertEqual(rows[0]['code'], 'BE')

    def test_create_out_of_domain_does_not_persist(self):
        self.access_model.create(
            {
                'model_id': self.partner_model.id,
                'allow_read': True,
                'allow_write': True,
                'domain': "[('is_company', '=', True)]",
            }
        )
        raised = False
        try:
            self.mixin._mcp_create_records(
                'res.partner',
                {'name': 'MCP_BOUNDARY', 'is_company': False},
            )
        except AccessError:
            raised = True
        self.assertTrue(raised)
        self.assertFalse(
            self.env['res.partner']
            .with_context(active_test=False)
            .search([('name', '=', 'MCP_BOUNDARY')]),
        )

    def test_create_in_domain_succeeds(self):
        self.access_model.create(
            {
                'model_id': self.partner_model.id,
                'allow_read': True,
                'allow_write': True,
                'domain': "[('is_company', '=', True)]",
            }
        )
        result = self.mixin._mcp_create_records(
            'res.partner',
            {'name': 'MCP_IN_DOMAIN', 'is_company': True},
        )
        self.assertTrue(result['id'])
        self.assertEqual(
            self.env['res.partner'].browse(result['id']).name,
            'MCP_IN_DOMAIN',
        )

    def test_domain_dynamic_user_context(self):
        self.access_model.create(
            {
                'model_id': self.user_model.id,
                'allow_read': True,
                'domain': "[('id', '=', user.id)]",
            }
        )
        self.assertEqual(
            self.access_model._get_model_domain('res.users'),
            [('id', '=', self.env.user.id)],
        )

    # ----------------------------------------------------------
    # Tests: export_records record domain
    # ----------------------------------------------------------

    def test_export_records_applies_domain(self):
        self.access_model.create(
            {
                'model_id': self.country_model.id,
                'allow_read': True,
                'domain': "[('code', '=', 'BE')]",
            }
        )
        result = self.mixin._mcp_export_records(
            'res.country',
            fields=['code'],
            domain=[('code', 'in', ['BE', 'FR'])],
        )
        self.assertEqual(result['row_count'], 1)

    def test_export_records_blocks_out_of_domain_ids(self):
        self.access_model.create(
            {
                'model_id': self.country_model.id,
                'allow_read': True,
                'domain': "[('code', '=', 'BE')]",
            }
        )
        with self.assertRaises(AccessError):
            self.mixin._mcp_export_records(
                'res.country',
                fields=['code'],
                ids=[self.env.ref('base.fr').id],
            )

    # ----------------------------------------------------------
    # Tests: call_method record domain
    # ----------------------------------------------------------

    def test_call_method_blocks_out_of_domain(self):
        self.access_model.create(
            {
                'model_id': self.partner_model.id,
                'allow_read': True,
                'allow_write': True,
                'domain': "[('is_company', '=', True)]",
            }
        )
        partner = self.env['res.partner'].create(
            {'name': 'MCP_CM_OUT', 'is_company': False},
        )
        with self.assertRaises(AccessError):
            self.mixin._mcp_call_method(
                'res.partner',
                'write',
                ids=[partner.id],
                args='[{"comment": "x"}]',
            )
        self.assertFalse(partner.comment)

    def test_call_method_allows_in_domain(self):
        self.access_model.create(
            {
                'model_id': self.partner_model.id,
                'allow_read': True,
                'allow_write': True,
                'domain': "[('is_company', '=', True)]",
            }
        )
        partner = self.env['res.partner'].create(
            {'name': 'MCP_CM_IN', 'is_company': True},
        )
        self.mixin._mcp_call_method(
            'res.partner',
            'write',
            ids=[partner.id],
            args='[{"comment": "ok"}]',
        )
        self.assertEqual(partner.comment, '<p>ok</p>')

    # ----------------------------------------------------------
    # Tests: print_report allowlist and record domain
    # ----------------------------------------------------------

    def test_print_report_blocks_unlisted_model(self):
        self.access_model.create(
            {
                'model_id': self.partner_model.id,
                'allow_read': True,
            }
        )
        report = self.env['ir.actions.report'].create(
            {
                'name': 'MCP Country Report',
                'model': 'res.country',
                'report_name': 'muk_mcp_access.test_country_report',
                'report_type': 'qweb-html',
            }
        )
        with self.assertRaises(AccessError):
            self.mixin._mcp_print_report(report.id, [self.env.ref('base.be').id])

    def test_print_report_blocks_out_of_domain(self):
        self.access_model.create(
            {
                'model_id': self.country_model.id,
                'allow_read': True,
                'domain': "[('code', '=', 'BE')]",
            }
        )
        report = self.env['ir.actions.report'].create(
            {
                'name': 'MCP Country Report',
                'model': 'res.country',
                'report_name': 'muk_mcp_access.test_country_report',
                'report_type': 'qweb-html',
            }
        )
        with self.assertRaises(AccessError):
            self.mixin._mcp_print_report(report.id, [self.env.ref('base.fr').id])

    # ----------------------------------------------------------
    # Tests: archived entries
    # ----------------------------------------------------------

    def test_archived_entry_not_counted(self):
        self.access_model.create(
            {
                'model_id': self.partner_model.id,
                'active': False,
            }
        )
        self.assertFalse(self.access_model._is_active())
        self.assertTrue(
            self.access_model._is_model_allowed('anything'),
        )
