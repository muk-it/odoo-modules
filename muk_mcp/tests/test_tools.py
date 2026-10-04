from __future__ import annotations

import json
from unittest.mock import patch

from odoo import api, models
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests import new_test_user

from odoo.addons.muk_mcp.core.tool import (
    get_tool_index,
    invalidate_registry_cache,
    mcp_tool,
)
from odoo.addons.muk_mcp.tests.common import MCPToolCase
from odoo.addons.muk_mcp.tools.exception import MCPScopeDenied

PNG = (
    'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQ'
    'VQYV2NgAAIAAAUAAarVyFEAAAAASUVORK5CYII='
)


@api.model
@mcp_tool(name='mcp_test_records', visibility=['app'])
def _mcp_test_records(self) -> models.BaseModel:
    """Return the partners named like the test fixtures."""
    return self.env['res.partner'].search([('name', '=like', 'MCP Partner _')])


@mcp_tool(name='mcp_test_records')
def _mcp_test_duplicate(self) -> None:
    """Clash with the name of another tool."""


class TestMcpTools(MCPToolCase):
    """Cover the built-in tools, the tool registry and the tool call pipeline."""

    # ----------------------------------------------------------
    # Setup
    # ----------------------------------------------------------

    @classmethod
    def setUpClass(cls) -> None:
        """Create a user restricted to two of three companies and their partners."""
        super().setUpClass()
        cls.log_model = cls.env['muk_mcp.log']
        cls.company_a, cls.company_b, cls.company_c = cls.env['res.company'].create(
            [{'name': f'MCP Tool Company {letter}'} for letter in 'ABC'],
        )
        cls.user = new_test_user(
            cls.env,
            login='mcp_tool_user',
            company_id=cls.company_a.id,
            company_ids=[(6, 0, [cls.company_a.id, cls.company_b.id])],
        )
        cls.partners = cls.env['res.partner'].create(
            [
                {'name': f'MCP Partner {company.name[-1]}', 'company_id': company.id}
                for company in (cls.company_a, cls.company_b, cls.company_c)
            ],
        )
        cls.partner_a, cls.partner_b, cls.partner_c = cls.partners
        cls.domain = [['id', 'in', cls.partners.ids]]

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    def _patch_mixin(self, **methods: object) -> None:
        """Add ``methods`` to the MCP mixin for the duration of the test."""
        mixin_cls = type(self.env['muk_mcp.mixin'])
        for name, method in methods.items():
            setattr(mixin_cls, name, method)
            self.addCleanup(delattr, mixin_cls, name)
        invalidate_registry_cache(self.env)
        self.addCleanup(invalidate_registry_cache, self.env)

    # ----------------------------------------------------------
    # Tests
    # ----------------------------------------------------------

    def test_introspection_tools(self):
        models_found = self.call_tool(
            'list_models', {'search': 'res.partn', 'limit': 5}
        )
        self.assertIn('res.partner', [entry['model'] for entry in models_found])
        self.assertTrue(all('res.partn' in entry['model'] for entry in models_found))
        modules = self.call_tool('list_modules', {'search': 'muk_mcp'})
        self.assertIn('muk_mcp', [module['name'] for module in modules])
        fields = self.call_tool('describe_model', {'model': 'res.partner'})
        self.assertEqual(fields['name']['type'], 'char')
        info = self.call_tool('system_info')
        self.assertEqual(info['database'], self.env.cr.dbname)
        self.assertIn(info['edition'], ('community', 'enterprise'))
        languages = self.call_tool('list_languages')
        self.assertIn('en_US', [language['code'] for language in languages])
        whoami = self.call_tool('whoami', user=self.user)
        self.assertEqual(whoami['uid'], self.user.id)
        self.assertEqual(whoami['company_id'], self.company_a.id)
        self.assertEqual(
            [company['id'] for company in whoami['companies']],
            (self.company_a | self.company_b).sorted('sequence').ids,
        )

    def test_domains_are_accepted_in_every_encoding(self):
        domain = [['id', '=', self.partner_a.id]]
        for encoded in (
            domain,
            json.dumps(domain),
            json.dumps(json.dumps(domain)),
            str([('id', '=', self.partner_a.id)]),
        ):
            with self.subTest(encoded):
                result = self.call_tool(
                    'search_count',
                    {'model': 'res.partner', 'domain': encoded},
                )
                self.assertEqual(result, {'count': 1})

    def test_binary_values_are_returned_as_resource_uris(self):
        self.partner_a.image_1920 = PNG
        uri = f'odoo://record/res.partner/{self.partner_a.id}/image_1920'
        arguments = {'model': 'res.partner', 'fields': ['name', 'image_1920']}
        rows = self.call_tool('read_records', {**arguments, 'ids': self.partner_a.id})
        self.assertEqual(rows[0]['image_1920'], uri)
        rows = self.call_tool(
            'search_read',
            {**arguments, 'domain': [['id', '=', self.partner_a.id]]},
        )
        self.assertEqual(
            rows,
            [{'id': self.partner_a.id, 'name': 'MCP Partner A', 'image_1920': uri}],
        )

    def test_crud_round_trip_is_audited(self):
        model = 'res.partner.category'
        created = self.call_tool(
            'create_records', {'model': model, 'values': {'name': 'MCP Tag'}}
        )
        record = self.env[model].browse(created['id'])
        self.assertEqual(created['display_name'], 'MCP Tag')
        updated = self.call_tool(
            'update_records',
            {'model': model, 'ids': [record.id], 'values': {'name': 'MCP Tag 2'}},
        )
        self.assertEqual(updated, {'success': True, 'ids': [record.id]})
        self.assertEqual(record.name, 'MCP Tag 2')
        rows = self.call_tool(
            'read_records',
            {'model': model, 'ids': [record.id], 'fields': ['name']},
        )
        self.assertEqual(rows, [{'id': record.id, 'name': 'MCP Tag 2'}])
        groups = self.call_tool(
            'read_group',
            {
                'model': 'res.partner',
                'domain': self.domain,
                'groupby': ['company_id'],
                'aggregates': ['id:count'],
            },
        )
        self.assertEqual([group['__count'] for group in groups], [1, 1, 1])
        deleted = self.call_tool('delete_records', {'model': model, 'ids': [record.id]})
        self.assertEqual(deleted, {'success': True, 'deleted_ids': [record.id]})
        self.assertFalse(record.exists())
        logs = self.log_model.search(
            [('tool_name', 'in', ('create_records', 'update_records'))]
        )
        self.assertEqual(
            sorted(
                (log.tool_name, log.status, log.model_name, log.res_id, log.res_ids)
                for log in logs
            ),
            [
                ('create_records', 'ok', model, record.id, [record.id]),
                ('update_records', 'ok', model, record.id, [record.id]),
            ],
        )

    def test_chatter_tools(self):
        posted = self.call_tool(
            'post_message',
            {
                'model': 'res.partner',
                'id': self.partner_a.id,
                'body': '<p>Hello</p>',
                'type': 'note',
            },
        )
        message = self.env['mail.message'].browse(posted['id'])
        self.assertEqual(message.subtype_id, self.env.ref('mail.mt_note'))
        messages = self.call_tool(
            'get_messages', {'model': 'res.partner', 'id': self.partner_a.id}
        )
        self.assertIn('<p>Hello</p>', [entry['body'] for entry in messages])
        log = self.log_model.search([('tool_name', '=', 'post_message')])
        self.assertEqual(log.res_id, self.partner_a.id)

    def test_invalid_calls_raise_user_errors(self):
        for name, arguments, message in (
            ('no_such_tool', {}, 'Tool not found'),
            ('search_read', ['res.partner'], 'must be a JSON object'),
            ('search_read', {'model': 'no.such.model'}, 'not found'),
            ('read_records', {'model': 'res.partner', 'ids': []}, 'No record IDs'),
            (
                'read_records',
                {'model': 'res.partner', 'ids': 'abc'},
                'Invalid record ID',
            ),
            (
                'update_records',
                {'model': 'res.partner', 'ids': [], 'values': {}},
                'No record IDs',
            ),
            ('delete_records', {'model': 'res.partner', 'ids': []}, 'No record IDs'),
            (
                'read_group',
                {'model': 'res.partner', 'groupby': []},
                'groupby is required',
            ),
            (
                'read_group',
                {'model': 'res.partner', 'groupby': ['type'], 'fields': ['type']},
                'Expected input schema',
            ),
            (
                'call_method',
                {'model': 'res.partner', 'method': '_check_company'},
                'Private',
            ),
            (
                'call_method',
                {'model': 'res.partner', 'method': 'no_such_method'},
                'does not exist',
            ),
        ):
            with self.subTest(name=name, arguments=arguments):
                with self.assertRaisesRegex(UserError, message):
                    self.call_tool(name, arguments)

    def test_forbidden_models_raise_access_errors(self):
        cron = self.env['ir.cron'].search([], limit=1)
        for name, arguments in (
            ('read_records', {'model': 'ir.cron', 'ids': cron.ids}),
            (
                'create_records',
                {'model': 'res.company', 'values': {'name': 'MCP Denied'}},
            ),
            (
                'update_records',
                {
                    'model': 'res.company',
                    'ids': self.company_a.ids,
                    'values': {'name': 'X'},
                },
            ),
            ('delete_records', {'model': 'res.company', 'ids': self.company_c.ids}),
        ):
            with self.subTest(name), self.assertRaises(AccessError):
                self.call_tool(name, arguments, user=self.user)

    def test_record_rules_apply_to_every_read_tool(self):
        allowed = (self.partner_a | self.partner_b).ids
        rows = self.call_tool(
            'search_read',
            {'model': 'res.partner', 'domain': self.domain, 'fields': ['name']},
            user=self.user,
        )
        self.assertEqual(sorted(row['id'] for row in rows), allowed)
        count = self.call_tool(
            'search_count',
            {'model': 'res.partner', 'domain': self.domain},
            user=self.user,
        )
        self.assertEqual(count, {'count': 2})
        groups = self.call_tool(
            'read_group',
            {'model': 'res.partner', 'domain': self.domain, 'groupby': ['company_id']},
            user=self.user,
        )
        self.assertEqual(
            sorted(group['company_id'][0] for group in groups),
            (self.company_a | self.company_b).ids,
        )
        narrowed = self.call_tool(
            'search_read',
            {
                'model': 'res.partner',
                'domain': self.domain,
                'fields': ['name'],
                'context': {'allowed_company_ids': self.company_a.ids},
            },
            user=self.user,
        )
        self.assertEqual([row['id'] for row in narrowed], self.partner_a.ids)
        for name, arguments in (
            ('read_records', {'model': 'res.partner', 'ids': self.partner_c.ids}),
            (
                'search_read',
                {
                    'model': 'res.partner',
                    'domain': self.domain,
                    'context': {'allowed_company_ids': self.company_c.ids},
                },
            ),
        ):
            with self.subTest(name), self.assertRaises(AccessError):
                self.call_tool(name, arguments, user=self.user)

    def test_get_access_rights_lists_the_access_rows(self):
        result = self.call_tool(
            'get_access_rights', {'model': 'res.company'}, user=self.user
        )
        self.assertEqual(
            result['current_user_rights'],
            {'read': True, 'write': False, 'create': False, 'unlink': False},
        )
        rows = self.env['ir.access'].search([('model_id.model', '=', 'res.company')])
        self.assertEqual(
            sorted(row['id'] for row in result['access_rules']), sorted(rows.ids)
        )
        self.assertEqual(
            set(result['access_rules'][0]),
            {'id', 'name', 'group_id', 'operation', 'domain'},
        )

    def test_read_scope_allows_only_read_tools(self):
        self.env['muk_mcp.tool'].create(
            {
                'name': 'mcp_test_db_write',
                'category': 'write',
                'description': 'X',
                'code': 'result = 1',
            },
        )
        self.assertEqual(
            self.call_tool('search_count', {'model': 'res.users'}, scope='read')[
                'count'
            ],
            self.env['res.users'].search_count([]),
        )
        for name, arguments in (
            ('create_records', {'model': 'res.partner', 'values': {'name': 'X'}}),
            ('mcp_test_db_write', {}),
        ):
            with self.subTest(name), self.assertRaises(MCPScopeDenied):
                self.call_tool(name, arguments, scope='read')

    def test_call_method_targets_records_and_model_methods(self):
        category = self.env['res.partner.category'].create({'name': 'MCP Call'})
        self.partner_c.active = False
        mixin_cls = type(self.env['muk_mcp.mixin'])
        with patch.object(
            mixin_cls, '_mcp_assert_records_allowed', autospec=True
        ) as hook:
            self.call_tool(
                'call_method',
                {
                    'model': 'res.partner.category',
                    'method': 'write',
                    'args': json.dumps([category.ids, {'name': 'MCP Called'}]),
                },
            )
            count = self.call_tool(
                'call_method',
                {
                    'model': 'res.partner',
                    'method': 'search_count',
                    'ids': self.partner_a.ids,
                    'args': json.dumps([self.domain]),
                    'kwargs': {'context': {'active_test': False}},
                },
            )
        self.assertEqual(category.name, 'MCP Called')
        self.assertEqual(count, 3)
        self.assertEqual(hook.call_count, 1)
        self.assertEqual(
            hook.call_args.args[1:], ('res.partner.category', category.ids)
        )
        self.call_tool(
            'call_method',
            {'model': 'res.partner.category', 'method': 'unlink', 'ids': category.ids},
        )
        self.assertFalse(category.exists())

    def test_context_overrides_reach_every_tool_kind(self):
        self.env['muk_mcp.tool'].create(
            {
                'name': 'mcp_test_context',
                'description': 'Return the probe flag.',
                'code': 'result = {"probe": env.context.get("mcp_probe")}',
            },
        )
        self.partner_c.active = False
        for name, arguments, expected in (
            ('mcp_test_context', {'context': {'mcp_probe': 'db'}}, {'probe': 'db'}),
            ('mcp_test_context', {'context': 'not-a-dict'}, {'probe': None}),
            (
                'search_count',
                {'model': 'res.partner', 'domain': self.domain},
                {'count': 2},
            ),
            (
                'search_count',
                {
                    'model': 'res.partner',
                    'domain': self.domain,
                    'context': {'active_test': False},
                },
                {'count': 3},
            ),
        ):
            with self.subTest(name=name, arguments=arguments):
                self.assertEqual(self.call_tool(name, arguments), expected)
        self.assertNotIn('mcp_probe', self.env.context)

    def test_registry_filters_the_listing(self):
        entry = {
            'kind': 'method',
            'model': 'muk_mcp.mixin',
            'method': '_mcp_whoami',
            'description': 'Probe.',
            'input_schema': {'type': 'object'},
            'category': 'read',
        }
        self.env.registry._muk_mcp_method_cache = {
            name: {**entry, 'registry': registry}
            for name, registry in (
                ('unscoped', None),
                ('mcp_only', 'mcp'),
                ('ai_only', 'ai'),
                ('shared', 'mcp, cron'),
            )
        }
        self.addCleanup(invalidate_registry_cache, self.env)
        for registry, expected in (
            (None, {'unscoped', 'mcp_only', 'ai_only', 'shared'}),
            ('mcp', {'unscoped', 'mcp_only', 'shared'}),
            ('cron', {'unscoped', 'shared'}),
            ('ghost', {'unscoped'}),
        ):
            with self.subTest(registry):
                tools = self.env['muk_mcp.tool'].get_tools(registry=registry)
                self.assertEqual(
                    {tool['name'] for tool in tools}
                    & set(self.env.registry._muk_mcp_method_cache),
                    expected,
                )
        self.assertEqual(
            get_tool_index(self.env)['unscoped']['input_schema'],
            {'type': 'object', 'properties': {}},
        )

    def test_decorated_methods_and_records_form_the_index(self):
        self._patch_mixin(_mcp_test_records=_mcp_test_records)
        listing = {tool['name']: tool for tool in self.env['muk_mcp.tool'].get_tools()}
        self.assertEqual(
            listing['mcp_test_records'],
            {
                'name': 'mcp_test_records',
                'description': 'Return the partners named like the test fixtures.',
                'inputSchema': {'type': 'object', 'properties': {}},
                'annotations': {'readOnlyHint': True},
                '_meta': {'ui': {'visibility': ['app']}},
            },
        )
        self.assertEqual(
            listing['create_records']['annotations'], {'readOnlyHint': False}
        )
        self.assertEqual(
            sorted(self.call_tool('mcp_test_records')),
            sorted([partner.id, partner.name] for partner in self.partners),
        )
        self.env['muk_mcp.tool'].create(
            {
                'name': 'mcp_test_records',
                'description': 'From the database.',
                'code': 'result = {"from": "db"}',
            },
        )
        playground = {
            tool['name']: tool
            for tool in self.env['muk_mcp.tool'].get_playground_tools()
        }
        self.assertEqual(playground['mcp_test_records']['kind'], 'db')
        self.assertEqual(self.call_tool('mcp_test_records'), {'from': 'db'})
        self._patch_mixin(_mcp_test_duplicate=_mcp_test_duplicate)
        with self.assertRaisesRegex(ValueError, 'Duplicate'):
            get_tool_index(self.env)

    def test_sandbox_logger_reaches_the_tool_logger(self):
        self.env['muk_mcp.tool'].create(
            {
                'name': 'mcp_test_logger',
                'description': 'Log at every level.',
                'code': (
                    'logger.info("i")\nlogger.warning("w")\n'
                    'logger.error("e")\nlogger.exception("x")\nresult = 1'
                ),
            },
        )
        name = 'odoo.addons.muk_mcp.models.tool (mcp_test_logger)'
        with self.assertLogs(name, 'INFO') as logs:
            self.call_tool('mcp_test_logger')
        self.assertEqual(
            [(record.levelname, record.getMessage()) for record in logs.records],
            [('INFO', 'i'), ('WARNING', 'w'), ('ERROR', 'e'), ('ERROR', 'x')],
        )
        self.assertTrue(logs.records[-1].exc_info)

    def test_tool_definitions_are_validated(self):
        for values in (
            {'code': 'this is not python !!!'},
            {'code': 'result = 1', 'input_schema': '{not json'},
        ):
            with self.subTest(values), self.assertRaises(ValidationError):
                self.env['muk_mcp.tool'].create(
                    {'name': 'mcp_test_bad', 'description': 'X', **values}
                )
