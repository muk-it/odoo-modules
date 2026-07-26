from __future__ import annotations

import base64
import json
from typing import Any
from unittest.mock import patch

from odoo.exceptions import AccessError
from odoo.tests import common, tagged
from odoo.tests.common import new_test_user


@tagged('post_install', '-at_install')
class TestMcpAclIsolation(common.TransactionCase):
    """Cover record rules, model ACLs and company scoping on tool-reachable code."""

    # ----------------------------------------------------------
    # Setup
    # ----------------------------------------------------------

    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls.tool_model = cls.env['muk_mcp.tool']
        cls.log_model = cls.env['muk_mcp.log']
        cls.company_a = cls.env['res.company'].create({'name': 'MCP Company A'})
        cls.company_b = cls.env['res.company'].create({'name': 'MCP Company B'})
        cls.company_c = cls.env['res.company'].create({'name': 'MCP Company C'})
        cls.user = new_test_user(
            cls.env,
            login='mcp_restricted',
            groups='base.group_user',
            company_id=cls.company_a.id,
            company_ids=[(6, 0, [cls.company_a.id, cls.company_b.id])],
        )
        cls.partner_a = cls.env['res.partner'].create(
            {'name': 'MCP ACL A', 'company_id': cls.company_a.id},
        )
        cls.partner_b = cls.env['res.partner'].create(
            {'name': 'MCP ACL B', 'company_id': cls.company_b.id},
        )
        cls.partner_c = cls.env['res.partner'].create(
            {'name': 'MCP ACL C', 'company_id': cls.company_c.id},
        )
        cls.partner_ids = [cls.partner_a.id, cls.partner_b.id, cls.partner_c.id]
        cls.env['ir.ui.view'].create(
            {
                'type': 'qweb',
                'name': 'muk_mcp.test_acl_report',
                'key': 'muk_mcp.test_acl_report',
                'arch': (
                    '<t t-name="muk_mcp.test_acl_report">'
                    '<t t-foreach="docs" t-as="d">'
                    '<t t-esc="d.name"/>|'
                    '</t>'
                    '</t>'
                ),
            },
        )
        cls.report = cls.env['ir.actions.report'].create(
            {
                'name': 'MCP ACL Report',
                'report_name': 'muk_mcp.test_acl_report',
                'report_type': 'qweb-text',
                'model': 'res.partner',
            },
        )

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    def _call_as_user(
        self,
        name: str,
        arguments: dict[str, Any],
        **kwargs: Any,
    ) -> Any:
        """Run a tool as the restricted test user and decode its JSON result."""
        text, _info = self.tool_model._call(
            name,
            arguments,
            self.env(user=self.user),
            **kwargs,
        )
        return json.loads(text)

    def _call_as_admin(
        self,
        name: str,
        arguments: dict[str, Any],
        **kwargs: Any,
    ) -> Any:
        """Run a tool in the privileged test environment and decode its result."""
        text, _info = self.tool_model._call(name, arguments, self.env, **kwargs)
        return json.loads(text)

    # ----------------------------------------------------------
    # Tests: record rules
    # ----------------------------------------------------------

    def test_search_read_honours_the_multi_company_rule(self):
        rows = self._call_as_user(
            'search_read',
            {
                'model': 'res.partner',
                'domain': [['id', 'in', self.partner_ids]],
                'fields': ['name'],
            },
        )
        self.assertEqual(
            {row['id'] for row in rows},
            {self.partner_a.id, self.partner_b.id},
        )

    def test_search_count_honours_the_multi_company_rule(self):
        result = self._call_as_user(
            'search_count',
            {
                'model': 'res.partner',
                'domain': [['id', 'in', self.partner_ids]],
            },
        )
        self.assertEqual(result['count'], 2)

    def test_read_group_honours_the_multi_company_rule(self):
        groups = self._call_as_user(
            'read_group',
            {
                'model': 'res.partner',
                'domain': [['id', 'in', self.partner_ids]],
                'groupby': ['company_id'],
            },
        )
        self.assertEqual(
            {group['company_id'][0] for group in groups},
            {self.company_a.id, self.company_b.id},
        )
        self.assertEqual(sum(group['__count'] for group in groups), 2)

    def test_read_records_outside_the_allowed_companies_raises(self):
        with self.assertRaises(AccessError):
            self._call_as_user(
                'read_records',
                {
                    'model': 'res.partner',
                    'ids': [self.partner_c.id],
                    'fields': ['name'],
                },
            )

    # ----------------------------------------------------------
    # Tests: model access rights
    # ----------------------------------------------------------

    def test_read_records_on_a_forbidden_model_raises(self):
        cron = self.env['ir.cron'].search([], limit=1)
        self.assertTrue(cron)
        with self.assertRaises(AccessError):
            self._call_as_user('read_records', {'model': 'ir.cron', 'ids': cron.ids})

    def test_create_records_on_a_forbidden_model_raises(self):
        with self.assertRaises(AccessError):
            self._call_as_user(
                'create_records',
                {'model': 'res.company', 'values': {'name': 'MCP Denied'}},
            )

    def test_update_records_on_a_forbidden_model_raises(self):
        with self.assertRaises(AccessError):
            self._call_as_user(
                'update_records',
                {
                    'model': 'res.company',
                    'ids': [self.company_a.id],
                    'values': {'name': 'MCP Denied'},
                },
            )

    def test_delete_records_on_a_forbidden_model_raises(self):
        with self.assertRaises(AccessError):
            self._call_as_user(
                'delete_records',
                {'model': 'res.company', 'ids': [self.company_c.id]},
            )

    # ----------------------------------------------------------
    # Tests: company context overrides
    # ----------------------------------------------------------

    def test_allowed_company_context_narrows_the_result(self):
        rows = self._call_as_user(
            'search_read',
            {
                'model': 'res.partner',
                'domain': [['id', 'in', self.partner_ids]],
                'fields': ['name'],
                'context': {'allowed_company_ids': [self.company_a.id]},
            },
        )
        self.assertEqual([row['id'] for row in rows], [self.partner_a.id])

    def test_unauthorized_company_context_does_not_widen_access(self):
        with self.assertRaises(AccessError):
            self._call_as_user(
                'search_read',
                {
                    'model': 'res.partner',
                    'domain': [['id', 'in', self.partner_ids]],
                    'fields': ['name'],
                    'context': {'allowed_company_ids': [self.company_c.id]},
                },
            )

    # ----------------------------------------------------------
    # Tests: audit log isolation
    # ----------------------------------------------------------

    def test_user_only_sees_their_own_audit_log_rows(self):
        mine = self.log_model.create(
            {
                'user_id': self.user.id,
                'method': 'tools/call',
                'tool_name': 'mcp_acl_mine',
                'status': 'ok',
            },
        )
        theirs = self.log_model.create(
            {
                'user_id': self.env.ref('base.user_admin').id,
                'method': 'tools/call',
                'tool_name': 'mcp_acl_theirs',
                'request_data': '{"secret": "value"}',
                'status': 'ok',
            },
        )
        visible = self.log_model.with_user(self.user).search(
            [('id', 'in', (mine + theirs).ids)],
        )
        self.assertEqual(visible, mine)
        with self.assertRaises(AccessError):
            theirs.with_user(self.user).read(['request_data'])

    # ----------------------------------------------------------
    # Tests: read scope reaches export and report rendering
    # ----------------------------------------------------------

    def test_read_scope_key_can_export_any_readable_model(self):
        result = self._call_as_admin(
            'export_records',
            {
                'model': 'res.partner',
                'fields': ['name'],
                'ids': [self.partner_a.id],
            },
            enforce_scope='read',
        )
        content = base64.b64decode(result['content_base64']).decode('utf-8-sig')
        self.assertIn('MCP ACL A', content)

    def test_read_scope_key_can_render_any_report(self):
        result = self._call_as_admin(
            'print_report',
            {'report_ref': self.report.id, 'ids': [self.partner_a.id]},
            enforce_scope='read',
        )
        content = base64.b64decode(result['content_base64']).decode()
        self.assertIn('MCP ACL A|', content)

    # ----------------------------------------------------------
    # Tests: call_method reach
    # ----------------------------------------------------------

    def test_call_method_reaches_write(self):
        category = self.env['res.partner.category'].create({'name': 'MCP Call Write'})
        self._call_as_admin(
            'call_method',
            {
                'model': 'res.partner.category',
                'method': 'write',
                'ids': [category.id],
                'args': json.dumps([{'name': 'MCP Call Written'}]),
            },
        )
        self.assertEqual(category.name, 'MCP Call Written')

    def test_call_method_reaches_unlink(self):
        category = self.env['res.partner.category'].create({'name': 'MCP Call Unlink'})
        self._call_as_admin(
            'call_method',
            {
                'model': 'res.partner.category',
                'method': 'unlink',
                'ids': [category.id],
            },
        )
        self.assertFalse(category.exists())

    def test_call_method_skips_the_record_hook_for_api_model_methods(self):
        seen = []

        def _record(self, model, ids):
            seen.append((model, list(ids)))

        category = self.env['res.partner.category'].create({'name': 'MCP Call Hook'})
        mixin_cls = type(self.env['muk_mcp.mixin'])
        with patch.object(mixin_cls, '_mcp_assert_records_allowed', _record):
            self._call_as_admin(
                'call_method',
                {
                    'model': 'res.partner',
                    'method': 'search_count',
                    'ids': [self.partner_a.id],
                    'args': json.dumps([[]]),
                },
            )
            self.assertEqual(seen, [])
            self._call_as_admin(
                'call_method',
                {
                    'model': 'res.partner.category',
                    'method': 'write',
                    'ids': [category.id],
                    'args': json.dumps([{'name': 'MCP Call Hooked'}]),
                },
            )
        self.assertEqual(seen, [('res.partner.category', [category.id])])

    # ----------------------------------------------------------
    # Tests: introspection bypasses access control
    # ----------------------------------------------------------

    def test_list_models_ignores_model_access_rules(self):
        result = self._call_as_user('list_models', {'search': 'ir.cron', 'limit': 50})
        self.assertIn('ir.cron', [entry['model'] for entry in result])
        with self.assertRaises(AccessError):
            self.env['ir.cron'].with_user(self.user).check_access('read')

    def test_get_access_rights_reads_the_rule_list_with_sudo(self):
        result = self._call_as_user('get_access_rights', {'model': 'res.company'})
        self.assertEqual(
            result['current_user_rights'],
            {'read': True, 'write': False, 'create': False, 'unlink': False},
        )
        self.assertTrue(result['access_rules'])
        with self.assertRaises(AccessError):
            self.env['ir.model.access'].with_user(self.user).check_access('read')
