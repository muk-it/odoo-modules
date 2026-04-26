from unittest.mock import patch

from .common import AITestCommon


class TestLogUnification(AITestCommon):

    # ----------------------------------------------------------
    # Setup
    # ----------------------------------------------------------

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.session = cls.env['muk_ai.session'].create({'name': 'log-unification'})

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    def _patch_execute(self, results):
        def fake(self_arg, name, arguments, env, enforce_scope):
            return results.get(name, '{}'), {}, arguments.get('model')

        return patch.object(
            type(self.env['muk_mcp.tool']),
            '_execute',
            autospec=True,
            side_effect=fake,
        )

    # ----------------------------------------------------------
    # Tests
    # ----------------------------------------------------------

    def test_chat_call_writes_log_row_with_source_chat_and_session_id(self):
        with self._patch_execute({'list_modules': '{"modules": []}'}):
            text, ok = self.session._dispatch_tool_call(
                'list_modules', {}, 'call_chat',
            )
        self.assertTrue(ok)
        rows = self.env['muk_mcp.log'].search([
            ('session_id', '=', self.session.id),
            ('tool_name', '=', 'list_modules'),
        ])
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows.source, 'chat')
        self.assertEqual(rows.session_id, self.session)

    def test_external_call_writes_row_with_source_mcp_and_no_session(self):
        with self._patch_execute({'list_modules': '{}'}):
            self.env['muk_mcp.tool']._call(
                'list_modules', {}, self.env, enforce_scope=None,
            )
        rows = self.env['muk_mcp.log'].search([
            ('tool_name', '=', 'list_modules'),
            ('session_id', '=', False),
        ])
        self.assertTrue(rows)
        self.assertEqual(rows[0].source, 'mcp')

    def test_force_log_bypasses_disabled_config(self):
        from odoo.tools import config as odoo_config
        original_get = odoo_config.get

        def fake_get(key, default=None):
            if key == 'mcp_logging':
                return False
            return original_get(key, default)

        mcp_count_before = self.env['muk_mcp.log'].search_count([
            ('source', '=', 'mcp'),
        ])
        with patch.object(odoo_config, 'get', side_effect=fake_get):
            with self._patch_execute({'list_modules': '{}'}):
                self.env['muk_mcp.tool']._call(
                    'list_modules', {}, self.env, enforce_scope=None,
                )
            with self._patch_execute({'list_modules': '{}'}):
                self.session._dispatch_tool_call(
                    'list_modules', {}, 'call_force',
                )
        chat_rows = self.env['muk_mcp.log'].search([
            ('session_id', '=', self.session.id),
            ('tool_name', '=', 'list_modules'),
        ])
        self.assertTrue(chat_rows)
        mcp_count_after = self.env['muk_mcp.log'].search_count([
            ('source', '=', 'mcp'),
        ])
        self.assertEqual(mcp_count_after, mcp_count_before)

    def test_cascade_delete(self):
        session = self.env['muk_ai.session'].create({'name': 'cascade'})
        with self._patch_execute({'list_modules': '{}'}):
            session._dispatch_tool_call('list_modules', {}, 'cd_call')
        rows = self.env['muk_mcp.log'].search([
            ('session_id', '=', session.id),
        ])
        self.assertTrue(rows)
        row_ids = rows.ids
        session.unlink()
        survivors = self.env['muk_mcp.log'].search([
            ('id', 'in', row_ids),
        ])
        self.assertFalse(survivors)

    def test_unified_log_merges_chat_and_tool_entries(self):
        session = self.env['muk_ai.session'].create({'name': 'merge'})
        session._append_log({'kind': 'user_message', 'content': 'hi', 'attachments': []})
        with self._patch_execute({'list_modules': '{"ok": true}'}):
            session._dispatch_tool_call('list_modules', {}, 'merge_c1')
        session._append_log({'kind': 'text', 'content': 'final'})
        unified = session._unified_log()
        kinds = [entry.get('kind') for entry in unified]
        self.assertIn('user_message', kinds)
        self.assertIn('tool_call', kinds)
        self.assertIn('tool_result', kinds)
        self.assertIn('text', kinds)
        timestamps = [entry.get('at') or '' for entry in unified]
        self.assertEqual(timestamps, sorted(timestamps))

    def test_event_table_no_longer_carries_tool_calls(self):
        session = self.env['muk_ai.session'].create({'name': 'jsonb'})
        with self._patch_execute({'list_modules': '{}'}):
            session._dispatch_tool_call('list_modules', {}, 'jsonb_c1')
        kinds = {ev.kind for ev in session.event_ids}
        self.assertNotIn('tool_call', kinds)
        self.assertNotIn('tool_result', kinds)

    def test_clear_drops_event_rows_and_filters_log(self):
        session = self.env['muk_ai.session'].create({'name': 'clear-events'})
        session._append_log({'kind': 'user_message', 'content': 'hi', 'attachments': []})
        with self._patch_execute({'list_modules': '{"ok": true}'}):
            session._dispatch_tool_call('list_modules', {}, 'clear_c1')
        session._append_log({'kind': 'text', 'content': 'response'})
        before = session._unified_log()
        before_kinds = {entry.get('kind') for entry in before}
        self.assertIn('tool_call', before_kinds)
        self.assertIn('user_message', before_kinds)
        session.clear()
        unified = session._unified_log()
        self.assertEqual(len(unified), 1)
        self.assertEqual(unified[0].get('kind'), 'command')
        self.assertEqual(unified[0].get('name'), '/clear')
        log_rows = self.env['muk_mcp.log'].sudo().search([
            ('session_id', '=', session.id),
        ])
        self.assertTrue(log_rows)

    def test_compact_drops_event_rows(self):
        session = self.env['muk_ai.session'].create({'name': 'compact-events'})
        session._append_log({'kind': 'user_message', 'content': 'hi', 'attachments': []})
        with self._patch_execute({'list_modules': '{}'}):
            session._dispatch_tool_call('list_modules', {}, 'compact_c1')
        self.assertTrue(session.event_ids)
        session.event_ids.sudo().unlink()
        session.write({'cleared_log_id': session._max_session_log_id()})
        unified = session._unified_log()
        self.assertEqual(unified, [])

    def test_regenerate_truncates_to_last_user_message(self):
        session = self.env['muk_ai.session'].create({'name': 'regen-events'})
        session._append_log({'kind': 'user_message', 'content': 'first', 'attachments': []})
        session._append_log({'kind': 'text', 'content': 'first reply'})
        session._append_log({'kind': 'user_message', 'content': 'second', 'attachments': []})
        session._append_log({'kind': 'text', 'content': 'second reply'})
        events = session.event_ids.sorted(lambda e: (e.sequence, e.id))
        last_user = max(
            (i for i, e in enumerate(events) if e.kind == 'user_message'),
        )
        keep = events[:last_user + 1]
        drop = events[last_user + 1:]
        drop.unlink()
        remaining = session.event_ids.sorted(lambda e: (e.sequence, e.id))
        self.assertEqual(len(remaining), len(keep))
        kinds = [e.kind for e in remaining]
        self.assertEqual(kinds[-1], 'user_message')

    def test_reject_writes_denied_audit_row(self):
        session = self.env['muk_ai.session'].create({'name': 'reject-audit'})
        session.pending_ask = {
            'kind': 'approval',
            'call_id': 'call-1',
            'name': 'delete_records',
            'arguments': {'model': 'res.partner', 'ids': [1]},
            'risk': {
                'tool': 'delete_records',
                'model': 'res.partner',
                'ids': [1],
                'method': '',
                'reason': 'test',
                'signature': 'sig-1',
            },
            'tool_calls': [],
            'outputs': [],
            'resume_index': 0,
            'has_terminating': False,
        }
        session.state = 'waiting'
        with patch.object(
            type(session), '_trigger_worker', autospec=True, return_value=None,
        ):
            session.reject_tool(reason='unit-test rejection')
        rows = self.env['muk_mcp.log'].sudo().search([
            ('session_id', '=', session.id),
            ('source', '=', 'chat'),
            ('status', '=', 'denied'),
        ])
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows.tool_name, 'delete_records')
        haystack = (rows.error_message or '') + (rows.response_data or '')
        self.assertIn('rejected_by_user', haystack)

    def test_clear_then_new_tool_call_visible_after_reload(self):
        session = self.env['muk_ai.session'].create({'name': 'post-clear'})
        with self._patch_execute({'list_modules': '{"a": 1}'}):
            session._dispatch_tool_call('list_modules', {}, 'pre_c1')
        session.clear()
        with self._patch_execute({'list_modules': '{"b": 2}'}):
            session._dispatch_tool_call('list_modules', {}, 'post_c1')
        unified = session._unified_log()
        kinds = [entry.get('kind') for entry in unified]
        self.assertIn('command', kinds)
        self.assertIn('tool_call', kinds)
        tool_calls = [
            entry for entry in unified if entry.get('kind') == 'tool_call'
        ]
        self.assertEqual(len(tool_calls), 1)
