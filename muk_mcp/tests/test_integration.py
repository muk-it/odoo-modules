from __future__ import annotations

import json
import secrets

from odoo import fields
from odoo.tests import common, tagged
from odoo.tools import config

from odoo.addons.muk_mcp.core.tool import get_tool_index
from odoo.addons.muk_mcp.tools.encoder import encode_request
from odoo.addons.muk_mcp.tools.exception import MCPScopeDenied


@tagged('post_install', '-at_install')
class TestMcpIntegration(common.TransactionCase):
    """Exercise the full MCP stack through public model and tool APIs."""

    # ----------------------------------------------------------
    # Setup
    # ----------------------------------------------------------

    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls.key_model = cls.env['muk_mcp.key']
        cls.tool_model = cls.env['muk_mcp.tool']
        cls.session_model = cls.env['muk_mcp.session']
        cls.notification_model = cls.env['muk_mcp.notification']
        cls.read_token = secrets.token_urlsafe(32)
        cls.read_key = cls.key_model.sudo().create(
            {
                'name': 'Read-Only Test Key',
                'user_id': cls.env.ref('base.user_admin').id,
                'key_hash': cls.key_model._hash_key(cls.read_token),
                'key_prefix': cls.read_token[:8],
                'scope': 'read',
                'rate_limit': 0,
            },
        )

    # ----------------------------------------------------------
    # Tests: Session lifecycle
    # ----------------------------------------------------------

    def test_session_touch_updates_last_activity(self):
        old_time = fields.Datetime.subtract(
            fields.Datetime.now(),
            hours=1,
        )
        session = self.session_model.sudo().create(
            {
                'user_id': self.env.user.id,
                'initialized': True,
                'last_activity': old_time,
            },
        )
        session._touch()
        session.invalidate_recordset()
        self.assertGreater(session.last_activity, old_time)

    # ----------------------------------------------------------
    # Tests: Scope enforcement
    # ----------------------------------------------------------

    def test_read_scope_allows_read_tools(self):
        entry = get_tool_index(self.env).get('search_count')
        self.assertIsNotNone(entry)
        self.assertEqual(entry['category'], 'read')
        self.assertEqual(self.read_key.scope, 'read')
        self.tool_model._call(
            'search_count',
            {'model': 'res.partner'},
            self.env,
            enforce_scope='read',
        )

    def test_read_scope_blocks_write_tools(self):
        entry = get_tool_index(self.env).get('create_records')
        self.assertIsNotNone(entry)
        self.assertEqual(entry['category'], 'write')
        with self.assertRaises(MCPScopeDenied):
            self.tool_model._call(
                'create_records',
                {
                    'model': 'res.partner.category',
                    'values': {'name': 'scope-denied'},
                },
                self.env,
                enforce_scope='read',
            )

    # ----------------------------------------------------------
    # Tests: Tool execution through the full stack
    # ----------------------------------------------------------

    def test_tool_search_count(self):
        text, _info = self.tool_model._call(
            'search_count',
            {'model': 'res.partner', 'domain': []},
            self.env,
        )
        result = json.loads(text)
        self.assertIn('count', result)
        self.assertGreater(result['count'], 0)

    def test_tool_create_update_delete(self):
        text, _info = self.tool_model._call(
            'create_records',
            {
                'model': 'res.partner.category',
                'values': {'name': 'MCP Integration Test'},
            },
            self.env,
        )
        result = json.loads(text)
        self.assertIn('id', result)
        record_id = result['id']
        text, _info = self.tool_model._call(
            'update_records',
            {
                'model': 'res.partner.category',
                'ids': [record_id],
                'values': {'name': 'MCP Updated'},
            },
            self.env,
        )
        result = json.loads(text)
        self.assertTrue(result['success'])
        text, _info = self.tool_model._call(
            'delete_records',
            {
                'model': 'res.partner.category',
                'ids': [record_id],
            },
            self.env,
        )
        result = json.loads(text)
        self.assertTrue(result['success'])

    # ----------------------------------------------------------
    # Tests: Notifications
    # ----------------------------------------------------------

    def test_notification_push_to_all_sessions(self):
        session = self.session_model.sudo().create(
            {
                'user_id': self.env.user.id,
                'initialized': True,
            },
        )
        self.notification_model.push_to_all_sessions(
            'notifications/tools/list_changed',
        )
        notifications = self.notification_model.search(
            [
                ('session_id', '=', session.id),
            ],
        )
        self.assertTrue(notifications)
        self.assertEqual(
            notifications[0].method,
            'notifications/tools/list_changed',
        )
        self.assertFalse(notifications[0].delivered)

    def test_tool_change_triggers_notification(self):
        session = self.session_model.sudo().create(
            {
                'user_id': self.env.user.id,
                'initialized': True,
            },
        )
        tool = self.tool_model.sudo().create(
            {
                'name': 'test_notify_tool',
                'description': 'Test notification trigger',
                'category': 'read',
                'code': 'result = {}',
            },
        )
        notifications = self.notification_model.search(
            [
                ('session_id', '=', session.id),
                ('method', '=', 'notifications/tools/list_changed'),
            ],
        )
        self.assertTrue(notifications)
        tool.unlink()

    # ----------------------------------------------------------
    # Tests: Encoder
    # ----------------------------------------------------------

    def test_encoder_limits_attribute_size(self):
        old = config.options.get('muk_logging_attribute_limit')
        config['muk_logging_attribute_limit'] = 50
        try:
            data = {'long_field': 'x' * 500}
            result = encode_request(data)
            self.assertLess(len(result), 600)
        finally:
            if old is None:
                config.options.pop('muk_logging_attribute_limit', None)
            else:
                config['muk_logging_attribute_limit'] = old

    def test_encoder_limits_content_size(self):
        old = config.options.get('muk_logging_content_limit')
        config['muk_logging_content_limit'] = 200
        try:
            data = {'data': list(range(10000))}
            result = encode_request(data)
            self.assertLessEqual(len(result), 210)
            self.assertTrue(result.endswith('...'))
        finally:
            if old is None:
                config.options.pop('muk_logging_content_limit', None)
            else:
                config['muk_logging_content_limit'] = old

    # ----------------------------------------------------------
    # Tests: MCP chatter attribution
    # ----------------------------------------------------------

    def test_mcp_name_set_on_message(self):
        partner = self.env['res.partner'].create({'name': 'MCP Badge Test'})
        msg = partner.with_context(
            mcp_name='Test Key',
        ).message_post(body='Hello from MCP')
        self.assertEqual(msg.mcp_name, 'Test Key')

    def test_mcp_name_not_set_without_context(self):
        partner = self.env['res.partner'].create({'name': 'Normal Test'})
        msg = partner.message_post(body='Regular message')
        self.assertFalse(msg.mcp_name)
