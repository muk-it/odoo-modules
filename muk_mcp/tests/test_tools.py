from __future__ import annotations

import base64
import json
from datetime import date, timedelta
from typing import Any

from odoo import fields
from odoo.exceptions import UserError
from odoo.tests import common, tagged
from odoo.tests.common import new_test_user

from odoo.addons.muk_mcp.tools.parser import coerce_json_value

PNG = (
    'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQ'
    'VQYV2NgAAIAAAUAAarVyFEAAAAASUVORK5CYII='
)


@tagged('post_install', '-at_install')
class TestMcpTool(common.TransactionCase):
    """Verify the CRUD, introspection, and coercion behavior of MCP tools."""

    # ----------------------------------------------------------
    # Setup
    # ----------------------------------------------------------

    @classmethod
    def setUpClass(cls) -> None:
        """Create the user and partners the tools act on."""
        super().setUpClass()
        cls.tool_model = cls.env['muk_mcp.tool']
        cls.user = new_test_user(
            cls.env,
            login='mcp_tool_user',
            groups='base.group_user,base.group_partner_manager',
        )
        cls.partner_a, cls.partner_b = cls.env['res.partner'].create(
            [{'name': 'MCP Tool Partner A'}, {'name': 'MCP Tool Partner B'}],
        )

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    def _call(self, name: str, arguments: dict[str, Any], user: Any = None) -> Any:
        """Run the ``name`` tool in-process, as ``user`` if given, and decode it."""
        env = self.env(user=user) if user else self.env
        text, _info = env['muk_mcp.tool']._call(name, arguments, env)
        return json.loads(text)

    # ----------------------------------------------------------
    # Tests
    # ----------------------------------------------------------

    def test_get_tools_returns_active(self):
        by_name = {entry['name']: entry for entry in self.tool_model.get_tools()}
        self.assertIn('search_read', by_name)
        schema = by_name['search_read']['inputSchema']
        self.assertEqual(schema['type'], 'object')
        self.assertEqual(schema['required'], ['model'])
        self.assertEqual(schema['properties']['model']['type'], 'string')
        self.assertEqual(schema['properties']['limit']['type'], 'integer')
        self.assertEqual(schema['properties']['fields']['items']['type'], 'string')
        self.assertIn('Search for records', by_name['search_read']['description'])

    def test_list_models_handler(self):
        result = self._call('list_models', {'search': 'res.partner', 'limit': 10})
        self.assertIsInstance(result, list)
        self.assertIn('res.partner', [m['model'] for m in result])

    def test_list_modules_handler(self):
        result = self._call('list_modules', {'search': 'base'})
        self.assertIsInstance(result, list)
        self.assertTrue(any(m['name'] == 'base' for m in result))

    def test_describe_model_handler(self):
        result = self._call('describe_model', {'model': 'res.partner'})
        self.assertIn('name', result)
        self.assertIn('email', result)
        self.assertEqual(result['name']['type'], 'char')
        self.assertNotIn('help', result['is_company'])
        detail = self._call(
            'describe_model', {'model': 'res.partner', 'fields': ['is_company']}
        )
        self.assertEqual(list(detail), ['is_company'])
        self.assertIn('help', detail['is_company'])

    def test_search_read_handler(self):
        company = self.env['res.partner'].create(
            {
                'name': 'MCP Search Read Co',
                'email': 'searchread@example.com',
                'is_company': True,
            },
        )
        result = self._call(
            'search_read',
            {
                'model': 'res.partner',
                'domain': [['id', '=', company.id]],
                'fields': ['name', 'email'],
                'limit': 5,
            },
        )
        self.assertEqual(
            result,
            [
                {
                    'id': company.id,
                    'name': 'MCP Search Read Co',
                    'email': 'searchread@example.com',
                },
            ],
        )

    def test_search_count_handler(self):
        result = self._call('search_count', {'model': 'res.partner', 'domain': []})
        self.assertIn('count', result)
        self.assertGreater(result['count'], 0)

    def test_create_and_delete_handler(self):
        created = self._call(
            'create_records',
            {
                'model': 'res.partner.category',
                'values': {'name': 'MCP Test Category'},
            },
        )
        self.assertIn('id', created)
        deleted = self._call(
            'delete_records',
            {
                'model': 'res.partner.category',
                'ids': [created['id']],
            },
        )
        self.assertTrue(deleted['success'])

    def test_values_odoo_computes_itself_are_reported(self):
        created = self._call(
            'create_records',
            {
                'model': 'res.partner',
                'values': {'name': 'MCP Computed', 'complete_name': 'MCP Typed'},
            },
        )
        self.assertEqual(created['ignored_fields'], ['complete_name'])
        self.assertEqual(
            self.env['res.partner'].browse(created['id']).complete_name,
            'MCP Computed',
        )

    def test_update_handler(self):
        record = self.env['res.partner.category'].create({'name': 'MCP Update'})
        try:
            result = self._call(
                'update_records',
                {
                    'model': 'res.partner.category',
                    'ids': [record.id],
                    'values': {'name': 'MCP Updated'},
                },
            )
            self.assertTrue(result['success'])
            self.assertEqual(record.name, 'MCP Updated')
        finally:
            record.unlink()

    def test_read_handler(self):
        partner = self.env['res.partner'].search([], limit=1)
        self.assertTrue(partner)
        result = self._call(
            'read_records',
            {
                'model': 'res.partner',
                'ids': [partner.id],
                'fields': ['name'],
            },
        )
        self.assertEqual(result[0]['id'], partner.id)

    def test_whoami_handler(self):
        result = self._call('whoami', {})
        self.assertIn('uid', result)
        self.assertEqual(result['uid'], self.env.uid)
        self.assertIn('company_id', result)
        self.assertIn('groups', result)

    def test_system_info_handler(self):
        result = self._call('system_info', {})
        self.assertEqual(result['product'], 'Odoo')
        self.assertIn(result['edition'], ('community', 'enterprise'))
        self.assertEqual(result['database'], self.env.cr.dbname)
        self.assertIn('version', result)
        self.assertNotIn('languages', result)
        self.assertNotIn('modules', result)

    def test_list_languages_handler(self):
        result = self._call('list_languages', {})
        self.assertIsInstance(result, list)
        self.assertTrue(any(lang['code'] == 'en_US' for lang in result))
        self.assertTrue(all('code' in lang and 'name' in lang for lang in result))

    def test_get_access_rights_handler(self):
        user = new_test_user(
            self.env,
            login='mcp_rights_probe',
            groups='base.group_user',
        )
        text, _info = self.tool_model._call(
            'get_access_rights',
            {'model': 'ir.cron'},
            self.env(user=user),
        )
        result = json.loads(text)
        self.assertEqual(result['model'], 'ir.cron')
        self.assertEqual(
            result['current_user_rights'],
            {'read': False, 'write': False, 'create': False, 'unlink': False},
        )
        self.assertTrue(result['access_rules'])

    def test_read_group_handler(self):
        category = self.env['res.partner.category'].create({'name': 'MCP Grouped'})
        for index in range(3):
            self.env['res.partner'].create(
                {
                    'name': 'MCP Group Member %d' % index,
                    'category_id': [(4, category.id)],
                },
            )
        result = self._call(
            'read_group',
            {
                'model': 'res.partner',
                'domain': [['category_id', '=', category.id]],
                'groupby': ['category_id'],
            },
        )
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]['__count'], 3)
        self.assertEqual(result[0]['category_id'][0], category.id)

    def test_read_records_swaps_binary_field_to_uri(self):
        png_b64 = (
            'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQ'
            'VQYV2NgAAIAAAUAAarVyFEAAAAASUVORK5CYII='
        )
        partner = self.env['res.partner'].create(
            {
                'name': 'Bin',
                'image_1920': png_b64,
            },
        )
        result = self._call(
            'read_records',
            {
                'model': 'res.partner',
                'ids': [partner.id],
                'fields': ['name', 'image_1920'],
            },
        )
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]['name'], 'Bin')
        self.assertEqual(
            result[0]['image_1920'],
            'odoo://record/res.partner/%d/image_1920' % partner.id,
        )

    def test_search_read_swaps_binary_field_to_uri(self):
        partner = self.env['res.partner'].create(
            {
                'name': 'Searchy',
                'image_1920': (
                    'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQ'
                    'VQYV2NgAAIAAAUAAarVyFEAAAAASUVORK5CYII='
                ),
            },
        )
        result = self._call(
            'search_read',
            {
                'model': 'res.partner',
                'domain': '[["id","=",%d]]' % partner.id,
                'fields': ['name', 'image_1920'],
            },
        )
        self.assertEqual(len(result), 1)
        self.assertEqual(
            result[0]['image_1920'],
            'odoo://record/res.partner/%d/image_1920' % partner.id,
        )

    def test_invalid_model_raises(self):
        with self.assertRaises(UserError):
            self._call(
                'search_read',
                {
                    'model': 'nonexistent.model',
                    'domain': [],
                },
            )

    def test_private_method_blocked(self):
        with self.assertRaisesRegex(UserError, 'Private methods'):
            self._call(
                'call_method',
                {
                    'model': 'res.partner',
                    'method': '_check_company',
                },
            )

    def test_method_not_found(self):
        with self.assertRaisesRegex(UserError, 'does not exist'):
            self._call(
                'call_method',
                {
                    'model': 'res.partner',
                    'method': 'totally_nonexistent_method_xyz',
                },
            )

    def test_empty_ids_raises(self):
        with self.assertRaises(UserError):
            self._call(
                'delete_records',
                {
                    'model': 'res.partner.category',
                    'ids': [],
                },
            )

    def test_read_group_without_groupby_raises(self):
        with self.assertRaisesRegex(UserError, 'groupby is required'):
            self._call(
                'read_group',
                {
                    'model': 'res.partner',
                    'groupby': [],
                },
            )

    def test_invalid_arguments_return_input_schema(self):
        with self.assertRaisesRegex(
            UserError, "unexpected keyword argument 'fields'"
        ) as ctx:
            self._call(
                'read_group',
                {
                    'model': 'res.partner',
                    'fields': ['is_company'],
                    'groupby': ['is_company'],
                },
            )
        self.assertIn('Expected input schema', str(ctx.exception))
        self.assertIn('"aggregates"', str(ctx.exception))

    def test_context_override_threads_through(self):
        archived = self.env['res.partner'].create(
            {
                'name': 'MCP Archived Partner',
                'active': False,
            },
        )
        try:
            active_default = self._call(
                'search_read',
                {
                    'model': 'res.partner',
                    'domain': [['id', '=', archived.id]],
                    'fields': ['id'],
                },
            )
            self.assertEqual(active_default, [])
            with_override = self._call(
                'search_read',
                {
                    'model': 'res.partner',
                    'domain': [['id', '=', archived.id]],
                    'fields': ['id'],
                    'context': {'active_test': False},
                },
            )
            self.assertEqual(len(with_override), 1)
            self.assertEqual(with_override[0]['id'], archived.id)
        finally:
            archived.unlink()

    def test_coerce_passthrough_non_string(self):
        self.assertEqual(coerce_json_value([['id', '=', 1]]), [['id', '=', 1]])
        self.assertEqual(coerce_json_value({'k': 'v'}), {'k': 'v'})
        self.assertEqual(coerce_json_value(42), 42)
        self.assertIsNone(coerce_json_value(None))

    def test_coerce_single_encoded_json(self):
        result = coerce_json_value('[["id", "=", 1]]')
        self.assertEqual(result, [['id', '=', 1]])

    def test_coerce_double_encoded_json(self):
        once = json.dumps([['id', '=', 1]])
        twice = json.dumps(once)
        self.assertEqual(coerce_json_value(twice), [['id', '=', 1]])

    def test_coerce_triple_encoded_json(self):
        payload = json.dumps(json.dumps(json.dumps([['id', '=', 1]])))
        self.assertEqual(coerce_json_value(payload), [['id', '=', 1]])

    def test_coerce_python_literal_fallback(self):
        result = coerce_json_value("[('id', '=', 1)]")
        self.assertEqual(result, [('id', '=', 1)])

    def test_coerce_python_literal_with_lowercase_booleans(self):
        result = coerce_json_value("{'active': true, 'name': null}")
        self.assertEqual(result, {'active': True, 'name': None})

    def test_coerce_invalid_returns_original(self):
        result = coerce_json_value('not-json-and-not-python')
        self.assertEqual(result, 'not-json-and-not-python')

    def test_coerce_empty_string_returns_empty_string(self):
        result = coerce_json_value('')
        self.assertEqual(result, '')

    def test_coerce_json_null_becomes_none(self):
        result = coerce_json_value('null')
        self.assertIsNone(result)

    def test_search_read_with_double_encoded_domain(self):
        partner = self.env['res.partner'].create(
            {
                'name': 'MCP Double Encoded Domain',
            },
        )
        try:
            inner = json.dumps([['id', '=', partner.id]])
            doubled = json.dumps(inner)
            result = self._call(
                'search_read',
                {
                    'model': 'res.partner',
                    'domain': doubled,
                    'fields': ['id', 'name'],
                },
            )
            self.assertEqual(len(result), 1)
            self.assertEqual(result[0]['id'], partner.id)
        finally:
            partner.unlink()

    def test_search_count_with_double_encoded_domain(self):
        partner = self.env['res.partner'].create(
            {
                'name': 'MCP Double Encoded Count',
            },
        )
        try:
            doubled = json.dumps(json.dumps([['id', '=', partner.id]]))
            result = self._call(
                'search_count',
                {
                    'model': 'res.partner',
                    'domain': doubled,
                },
            )
            self.assertEqual(result['count'], 1)
        finally:
            partner.unlink()

    def test_post_message_keeps_html_unescaped(self):
        partner = self.env['res.partner'].create(
            {
                'name': 'MCP HTML Body',
            },
        )
        result = self._call(
            'post_message',
            {
                'model': 'res.partner',
                'id': partner.id,
                'body': '<p>Hello <br/>world</p>',
            },
        )
        msg = self.env['mail.message'].browse(result['id'])
        self.assertIn('<p>', msg.body)
        self.assertNotIn('&lt;p&gt;', msg.body)

    def test_chatter_tools_post_and_read_back(self):
        for kind, subtype in (
            ('comment', 'mail.mt_comment'),
            ('note', 'mail.mt_note'),
        ):
            with self.subTest(kind=kind):
                result = self._call(
                    'post_message',
                    {
                        'model': 'res.partner',
                        'id': self.partner_a.id,
                        'body': f'<p>{kind}</p>',
                        'type': kind,
                    },
                    user=self.user,
                )
                message = self.env['mail.message'].browse(result['id'])
                self.assertEqual(message.subtype_id, self.env.ref(subtype))
        messages = self._call(
            'get_messages',
            {'model': 'res.partner', 'id': self.partner_a.id},
            user=self.user,
        )
        self.assertLessEqual(
            {'<p>note</p>', '<p>comment</p>'},
            {entry['body'] for entry in messages},
        )

    def test_schedule_activity_resolves_type_deadline_and_user(self):
        today = fields.Date.context_today(self.partner_a)
        todo = self.env.ref('mail.mail_activity_data_todo')
        call = self.env.ref('mail.mail_activity_data_call')
        other = new_test_user(self.env, login='mcp_tool_other')
        for arguments, kind, deadline, user, summary in (
            ({}, todo, today + timedelta(days=5), self.user, 'To-Do'),
            (
                {
                    'activity_type': 'call',
                    'date_deadline': '2030-01-02',
                    'user_id': other.id,
                    'summary': 'Ring back',
                    'note': '<p>About the offer</p>',
                },
                call,
                date(2030, 1, 2),
                other,
                'Ring back',
            ),
            (
                {'activity_type': 'mail.mail_activity_data_call'},
                call,
                today + timedelta(days=2),
                self.user,
                'Call',
            ),
            (
                {'activity_type': todo.id},
                todo,
                today + timedelta(days=5),
                self.user,
                'To-Do',
            ),
        ):
            with self.subTest(arguments=arguments):
                result = self._call(
                    'schedule_activity',
                    {'model': 'res.partner', 'id': self.partner_a.id, **arguments},
                    user=self.user,
                )
                activity = self.env['mail.activity'].browse(result['id'])
                self.assertEqual(
                    (activity.res_model, activity.res_id, activity.activity_type_id),
                    ('res.partner', self.partner_a.id, kind),
                )
                self.assertEqual(
                    (activity.date_deadline, activity.user_id, result['summary']),
                    (deadline, user, summary),
                )
        ring_back = self.partner_a.activity_ids.filtered(
            lambda activity: activity.summary == 'Ring back'
        )
        self.assertEqual(str(ring_back.note), '<p>About the offer</p>')

    def test_upload_file_writes_fields_and_attachments(self):
        raw = base64.b64decode(PNG)
        for extra, res_model, res_id in (
            (
                {'model': 'res.partner', 'id': self.partner_a.id},
                'res.partner',
                self.partner_a.id,
            ),
            ({}, False, 0),
            ({'data': f'data:image/png;base64,{PNG}', 'name': 'pixel'}, False, 0),
        ):
            with self.subTest(extra=extra):
                result = self._call(
                    'upload_file',
                    {'data': PNG, 'name': 'pixel.png', **extra},
                    user=self.user,
                )
                attachment = self.env['ir.attachment'].browse(result['id'])
                self.assertEqual(
                    (attachment.raw, attachment.mimetype), (raw, 'image/png')
                )
                self.assertEqual(
                    (attachment.res_model, attachment.res_id), (res_model, res_id)
                )
        result = self._call(
            'upload_file',
            {
                'data': PNG,
                'name': 'pixel.png',
                'model': 'res.partner',
                'id': self.partner_b.id,
                'field': 'image_1920',
            },
            user=self.user,
        )
        self.assertEqual(
            result['uri'], f'odoo://record/res.partner/{self.partner_b.id}/image_1920'
        )
        self.assertTrue(self.partner_b.image_1920)
        text = self._call(
            'upload_file', {'text': 'Hello', 'name': 'hello.txt'}, user=self.user
        )
        self.assertEqual(self.env['ir.attachment'].browse(text['id']).raw, b'Hello')
        self.env['ir.config_parameter'].sudo().set_param('web.max_file_upload_size', 10)
        with self.assertRaisesRegex(UserError, 'upload limit'):
            self._call('upload_file', {'data': PNG, 'name': 'pixel.png'})

    def test_chatter_activity_and_upload_errors_guide_the_caller(self):
        for name, arguments, message in (
            ('schedule_activity', {'model': 'res.country', 'id': 1}, 'no activities'),
            (
                'schedule_activity',
                {'model': 'res.partner', 'id': self.partner_a.id, 'user_id': 1},
                'not an active user',
            ),
            (
                'post_message',
                {'model': 'res.country', 'id': 1, 'body': 'x'},
                'no chatter',
            ),
            ('get_messages', {'model': 'res.partner', 'id': 999999999}, 'not found'),
            ('get_messages', {'model': 'no.such.model', 'id': 1}, 'not found'),
            (
                'schedule_activity',
                {'model': 'res.partner', 'id': 999999999},
                'not found',
            ),
            (
                'schedule_activity',
                {
                    'model': 'res.partner',
                    'id': self.partner_a.id,
                    'activity_type': 'Nope',
                },
                'not available.*To-Do',
            ),
            ('upload_file', {'data': 'not base64!', 'name': 'x'}, 'not valid base64'),
            ('upload_file', {'name': 'x'}, 'exactly one of file'),
            (
                'create_records',
                {'model': 'res.partner', 'values': [{'name': 'x'}, {'name': 'y'}]},
                'one JSON object',
            ),
            ('upload_file', {'data': PNG}, 'file name is required'),
            (
                'upload_file',
                {'data': PNG, 'name': 'x', 'field': 'image_1920'},
                'model and record ID are required',
            ),
            (
                'upload_file',
                {'data': PNG, 'name': 'x', 'model': 'res.partner'},
                'record ID is required',
            ),
            (
                'upload_file',
                {
                    'data': PNG,
                    'name': 'x',
                    'model': 'res.partner',
                    'id': self.partner_a.id,
                    'field': 'name',
                },
                'not a binary field',
            ),
        ):
            with self.subTest(name=name, arguments=arguments):
                with self.assertRaisesRegex(UserError, message):
                    self._call(name, arguments, user=self.user)
