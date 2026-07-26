from __future__ import annotations

import json
import secrets
from contextlib import AbstractContextManager
from typing import Any
from unittest.mock import MagicMock, patch

from odoo import api
from odoo.tests import common, tagged

from odoo.addons.muk_mcp.core.tool import invalidate_registry_cache, mcp_tool


@api.model
@mcp_tool(
    name='mcp_test_log_probe',
    description='No-op probe for log-path coverage.',
    input_schema={'type': 'object', 'properties': {}},
    category='read',
)
def _mcp_test_log_probe(self):
    return {'ok': True}


@tagged('post_install', '-at_install')
class TestMcpLog(common.TransactionCase):
    """Verify audit log records and the log rows emitted on tool execution."""

    # ----------------------------------------------------------
    # Setup
    # ----------------------------------------------------------

    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls.log_model = cls.env['muk_mcp.log']
        cls.tool_model = cls.env['muk_mcp.tool']
        cls.mixin_cls = type(cls.env['muk_mcp.mixin'])
        cls.mixin_cls._mcp_test_log_probe = _mcp_test_log_probe
        invalidate_registry_cache(cls.env)

    @classmethod
    def tearDownClass(cls) -> None:
        delattr(cls.mixin_cls, '_mcp_test_log_probe')
        invalidate_registry_cache(cls.env)
        super().tearDownClass()

    # ----------------------------------------------------------
    # Tests
    # ----------------------------------------------------------

    def test_log_persists_row(self):
        with self.enter_registry_test_mode():
            self.log_model.log(
                user_id=self.env.user.id,
                method='tools/call',
                tool_name='mcp_test_log_probe',
                status='ok',
            )
        record = self.log_model.search(
            [('tool_name', '=', 'mcp_test_log_probe')],
        )
        self.assertEqual(len(record), 1)
        self.assertEqual(record.method, 'tools/call')
        self.assertEqual(record.status, 'ok')
        self.assertEqual(record.user_id, self.env.user)

    def test_log_persists_payload_fields(self):
        with self.enter_registry_test_mode():
            self.log_model.log(
                user_id=self.env.user.id,
                method='tools/call',
                tool_name='mcp_test_log_payload',
                model_name='res.partner',
                res_id=42,
                res_ids=[42],
                status='ok',
                duration_ms=5,
                request_data=json.dumps({'model': 'res.partner'}),
                response_data=json.dumps([{'id': 1}]),
                ip_address='192.168.1.1',
            )
        record = self.log_model.search(
            [('tool_name', '=', 'mcp_test_log_payload')],
        )
        self.assertEqual(len(record), 1)
        self.assertEqual(record.model_name, 'res.partner')
        self.assertEqual(record.res_id, 42)
        self.assertEqual(record.res_ids, [42])
        self.assertEqual(record.duration_ms, 5)
        self.assertEqual(record.ip_address, '192.168.1.1')
        self.assertIn('res.partner', record.request_data)
        self.assertIn('"id": 1', record.response_data)

    # ----------------------------------------------------------
    # Tests: in-process tool._call records a log row
    # ----------------------------------------------------------

    def _captured_log(
        self,
    ) -> tuple[list[dict[str, Any]], AbstractContextManager[MagicMock]]:
        """Return the capture list and a patch recording every ``log`` call."""
        captured = []

        def _capture(_self, **values):
            captured.append(values)

        return captured, patch.object(
            type(self.log_model),
            'log',
            autospec=True,
            side_effect=_capture,
        )

    def test_tool_call_writes_log_on_success(self):
        captured, mock = self._captured_log()
        with mock:
            text, _info = self.tool_model._call(
                'mcp_test_log_probe',
                {},
                self.env,
            )
        self.assertEqual(json.loads(text), {'ok': True})
        self.assertEqual(len(captured), 1)
        entry = captured[0]
        self.assertEqual(entry['method'], 'tools/call')
        self.assertEqual(entry['tool_name'], 'mcp_test_log_probe')
        self.assertEqual(entry['user_id'], self.env.uid)
        self.assertEqual(entry['status'], 'ok')
        self.assertNotIn('key_name', entry)
        self.assertIn('duration_ms', entry)

    def test_tool_call_writes_log_on_error(self):
        captured, mock = self._captured_log()
        with mock, self.assertRaises(Exception):
            self.tool_model._call('mcp_test_unknown_tool', {}, self.env)
        self.assertEqual(len(captured), 1)
        self.assertEqual(captured[0]['status'], 'error')
        self.assertEqual(captured[0]['tool_name'], 'mcp_test_unknown_tool')

    # ----------------------------------------------------------
    # Tests: key snapshot must survive key deletion
    # ----------------------------------------------------------

    def test_key_snapshot_survives_key_deletion(self):
        key_model = self.env['muk_mcp.key']
        raw_token = secrets.token_urlsafe(32)
        key = key_model.create(
            {
                'name': 'Doomed Key',
                'user_id': self.env.user.id,
                'key_hash': key_model._hash_key(raw_token),
                'key_prefix': raw_token[:8],
            },
        )
        record = self.log_model.sudo().create(
            {
                'key_name': key.name,
                'key_prefix': key.key_prefix,
                'user_id': self.env.user.id,
                'method': 'tools/call',
                'tool_name': 'search_read',
                'status': 'ok',
            },
        )
        key.unlink()
        self.assertTrue(record.exists())
        self.assertEqual(record.key_name, 'Doomed Key')
        self.assertEqual(record.key_prefix, raw_token[:8])
        self.assertEqual(
            record.read(['key_name'])[0]['key_name'],
            'Doomed Key',
        )
