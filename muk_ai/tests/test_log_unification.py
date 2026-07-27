from __future__ import annotations

from contextlib import AbstractContextManager
from unittest.mock import MagicMock, patch

from odoo.tools import config as odoo_config

from odoo.addons.muk_ai.tests.common import AITestCommon


class TestLogUnification(AITestCommon):
    """Verify unified tool-call logging across MCP and agent paths."""

    # ----------------------------------------------------------
    # Setup
    # ----------------------------------------------------------

    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls.session = cls.env['muk_ai.session'].create({'name': 'log-unification'})

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    def _patch_execute(
        self, results: dict[str, str]
    ) -> AbstractContextManager[MagicMock]:
        """Patch tool execution to return a canned result per tool name.

        :param results: result per tool name; unlisted tools return ``{}``.
        """

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
            _text, ok = self.session._dispatch_tool_call(
                'list_modules',
                {},
                'call_chat',
            )
        self.assertTrue(ok)
        rows = self.env['muk_mcp.log'].search(
            [
                ('session_id', '=', self.session.id),
                ('tool_name', '=', 'list_modules'),
            ]
        )
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows.source, 'chat')
        self.assertEqual(rows.session_id, self.session)

    def test_external_call_writes_row_with_source_mcp_and_no_session(self):
        with self._patch_execute({'list_modules': '{}'}):
            self.env['muk_mcp.tool']._call(
                'list_modules',
                {},
                self.env,
                enforce_scope=None,
            )
        rows = self.env['muk_mcp.log'].search(
            [
                ('tool_name', '=', 'list_modules'),
                ('session_id', '=', False),
            ]
        )
        self.assertTrue(rows)
        self.assertEqual(rows[0].source, 'mcp')

    def test_cascade_delete(self):
        session = self.env['muk_ai.session'].create({'name': 'cascade'})
        with self._patch_execute({'list_modules': '{}'}):
            session._dispatch_tool_call('list_modules', {}, 'cd_call')
        rows = self.env['muk_mcp.log'].search(
            [
                ('session_id', '=', session.id),
            ]
        )
        self.assertTrue(rows)
        row_ids = rows.ids
        session.unlink()
        survivors = self.env['muk_mcp.log'].search(
            [
                ('id', 'in', row_ids),
            ]
        )
        self.assertFalse(survivors)

    def test_unified_events_reads_from_events(self):
        session = self.env['muk_ai.session'].create({'name': 'merge'})
        session._append_event(
            {'kind': 'user_message', 'content': 'hi', 'attachments': []}
        )
        session._record_tool_call(
            {
                'name': 'list_modules',
                'arguments': {},
                'call_id': 'merge_c1',
            }
        )
        session._record_tool_result(
            [],
            'merge_c1',
            'list_modules',
            '{"ok": true}',
        )
        session._append_event({'kind': 'text', 'content': 'final'})
        unified = session.fetch_events(limit=500)['events']
        kinds = [entry.get('kind') for entry in unified]
        self.assertIn('user_message', kinds)
        self.assertIn('tool_call', kinds)
        self.assertIn('tool_result', kinds)
        self.assertIn('text', kinds)
        self.assertEqual(len(unified), len(session.event_ids))
        timestamps = [entry.get('at') or '' for entry in unified]
        self.assertEqual(timestamps, sorted(timestamps))

    def test_tool_calls_persisted_to_events(self):
        session = self.env['muk_ai.session'].create({'name': 'jsonb'})
        with self._patch_execute({'list_modules': '{}'}):
            session._dispatch_tool_call('list_modules', {}, 'jsonb_c1')
        session._record_tool_call(
            {
                'name': 'list_modules',
                'arguments': {},
                'call_id': 'jsonb_c1',
            }
        )
        session._record_tool_result(
            [],
            'jsonb_c1',
            'list_modules',
            '{}',
        )
        kinds = {ev.kind for ev in session.event_ids}
        self.assertIn('tool_call', kinds)
        self.assertIn('tool_result', kinds)

    def test_clear_preserves_events_and_appends_marker(self):
        session = self.env['muk_ai.session'].create({'name': 'clear-events'})
        session._append_event(
            {'kind': 'user_message', 'content': 'hi', 'attachments': []}
        )
        with self._patch_execute({'list_modules': '{"ok": true}'}):
            session._dispatch_tool_call('list_modules', {}, 'clear_c1')
        session._record_tool_call(
            {
                'name': 'list_modules',
                'arguments': {},
                'call_id': 'clear_c1',
            }
        )
        session._record_tool_result(
            [],
            'clear_c1',
            'list_modules',
            '{"ok": true}',
        )
        session._append_event({'kind': 'text', 'content': 'response'})
        before_kinds = {ev.kind for ev in session.event_ids}
        self.assertIn('tool_call', before_kinds)
        self.assertIn('user_message', before_kinds)
        events_before = session.event_ids.sorted(lambda e: (e.sequence, e.id))
        audit_before = (
            self.env['muk_mcp.log']
            .sudo()
            .search(
                [
                    ('session_id', '=', session.id),
                ]
            )
        )
        self.assertTrue(audit_before)
        audit_ids = audit_before.ids
        session.clear()
        remaining = session.event_ids.sorted(lambda e: (e.sequence, e.id))
        self.assertEqual(
            len(remaining),
            len(events_before) + 1,
            '/clear must preserve prior event rows and append exactly one /clear marker',
        )
        for prior in events_before:
            self.assertIn(prior.id, remaining.ids)
        marker = remaining[-1]
        self.assertEqual(marker.kind, 'command')
        self.assertEqual((marker.payload or {}).get('name'), '/clear')
        self.assertTrue(session.cleared_at)
        audit_after = (
            self.env['muk_mcp.log']
            .sudo()
            .search(
                [
                    ('id', 'in', audit_ids),
                ]
            )
        )
        self.assertEqual(len(audit_after), len(audit_ids))

    def test_compact_drops_event_rows(self):
        session = self.env['muk_ai.session'].create({'name': 'compact-events'})
        session._append_event(
            {'kind': 'user_message', 'content': 'hi', 'attachments': []}
        )
        with self._patch_execute({'list_modules': '{}'}):
            session._dispatch_tool_call('list_modules', {}, 'compact_c1')
        self.assertTrue(session.event_ids)
        session.event_ids.sudo().unlink()
        unified = session.fetch_events(limit=500)['events']
        self.assertEqual(unified, [])

    def test_regenerate_truncates_to_last_user_message(self):
        session = self.env['muk_ai.session'].create({'name': 'regen-events'})
        session._append_event(
            {'kind': 'user_message', 'content': 'first', 'attachments': []}
        )
        session._append_event({'kind': 'text', 'content': 'first reply'})
        session._append_event(
            {'kind': 'user_message', 'content': 'second', 'attachments': []}
        )
        session._append_event({'kind': 'text', 'content': 'second reply'})
        events = session.event_ids.sorted(lambda e: (e.sequence, e.id))
        last_user = max(
            (i for i, e in enumerate(events) if e.kind == 'user_message'),
        )
        keep = events[: last_user + 1]
        drop = events[last_user + 1 :]
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
            type(session),
            '_trigger_worker',
            autospec=True,
            return_value=None,
        ):
            session.reject_tool(reason='unit-test rejection')
        rows = (
            self.env['muk_mcp.log']
            .sudo()
            .search(
                [
                    ('session_id', '=', session.id),
                    ('source', '=', 'chat'),
                    ('status', '=', 'denied'),
                ]
            )
        )
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows.tool_name, 'delete_records')
        haystack = (rows.error_message or '') + (rows.response_data or '')
        self.assertIn('rejected_by_user', haystack)

    def test_clear_then_new_tool_call_visible_after_reload(self):
        session = self.env['muk_ai.session'].create({'name': 'post-clear'})
        with self._patch_execute({'list_modules': '{"a": 1}'}):
            session._dispatch_tool_call('list_modules', {}, 'pre_c1')
        session._record_tool_call(
            {
                'name': 'list_modules',
                'arguments': {},
                'call_id': 'pre_c1',
            }
        )
        session._record_tool_result(
            [],
            'pre_c1',
            'list_modules',
            '{"a": 1}',
        )
        session.clear()
        with self._patch_execute({'list_modules': '{"b": 2}'}):
            session._dispatch_tool_call('list_modules', {}, 'post_c1')
        session._record_tool_call(
            {
                'name': 'list_modules',
                'arguments': {},
                'call_id': 'post_c1',
            }
        )
        session._record_tool_result(
            [],
            'post_c1',
            'list_modules',
            '{"b": 2}',
        )
        unified = session.fetch_events(limit=500)['events']
        kinds = [entry.get('kind') for entry in unified]
        self.assertIn('command', kinds)
        self.assertIn('tool_call', kinds)
        tool_calls = [entry for entry in unified if entry.get('kind') == 'tool_call']
        self.assertEqual(
            len(tool_calls),
            2,
            'Both pre-clear and post-clear tool_call events stay visible; /clear only resets LLM context',
        )
        command_indices = [i for i, k in enumerate(kinds) if k == 'command']
        self.assertEqual(len(command_indices), 1)
        boundary = command_indices[0]
        pre_kinds = kinds[:boundary]
        post_kinds = kinds[boundary + 1 :]
        self.assertIn('tool_call', pre_kinds)
        self.assertIn('tool_call', post_kinds)

    def test_chat_audit_respects_global_mcp_logging(self):
        original_get = odoo_config.get

        def fake_get(key, default=None):
            if key == 'mcp_logging':
                return False
            return original_get(key, default)

        session = self.env['muk_ai.session'].create({'name': 'audit-disabled'})
        before = (
            self.env['muk_mcp.log']
            .sudo()
            .search_count(
                [
                    ('session_id', '=', session.id),
                ]
            )
        )
        with patch.object(odoo_config, 'get', side_effect=fake_get):
            with self._patch_execute({'list_modules': '{}'}):
                text, ok = session._dispatch_tool_call(
                    'list_modules',
                    {},
                    'audit_c1',
                )
            session._record_tool_call(
                {
                    'name': 'list_modules',
                    'arguments': {},
                    'call_id': 'audit_c1',
                }
            )
            session._record_tool_result(
                [],
                'audit_c1',
                'list_modules',
                text,
            )
        self.assertTrue(ok)
        after = (
            self.env['muk_mcp.log']
            .sudo()
            .search_count(
                [
                    ('session_id', '=', session.id),
                ]
            )
        )
        self.assertEqual(after, before)
        kinds = {ev.kind for ev in session.event_ids}
        self.assertIn('tool_call', kinds)
        self.assertIn('tool_result', kinds)

    # ----------------------------------------------------------
    # Tests Pagination
    # ----------------------------------------------------------

    def test_unified_events_returns_latest_window(self):
        session = self.env['muk_ai.session'].create({'name': 'pag-window'})
        for index in range(250):
            session._append_event(
                {
                    'kind': 'text',
                    'content': f'msg-{index}',
                }
            )
        result = session.fetch_events(limit=100)
        self.assertEqual(len(result['events']), 100)
        self.assertTrue(result['has_more_older'])
        contents = [event['content'] for event in result['events']]
        self.assertEqual(contents[0], 'msg-150')
        self.assertEqual(contents[-1], 'msg-249')
        events_sorted = session.event_ids.sorted(
            lambda e: (e.sequence, e.id),
        )
        self.assertEqual(
            result['oldest_sequence'],
            events_sorted[150].sequence,
        )

    def test_unified_events_before_sequence_paginates_older(self):
        session = self.env['muk_ai.session'].create({'name': 'pag-older'})
        for index in range(250):
            session._append_event(
                {
                    'kind': 'text',
                    'content': f'msg-{index}',
                }
            )
        first_window = session.fetch_events(limit=100)
        older = session.fetch_events(
            limit=100,
            before_sequence=first_window['oldest_sequence'],
        )
        self.assertEqual(len(older['events']), 100)
        self.assertTrue(older['has_more_older'])
        contents = [event['content'] for event in older['events']]
        self.assertEqual(contents[0], 'msg-50')
        self.assertEqual(contents[-1], 'msg-149')

    def test_unified_events_below_limit_no_more(self):
        session = self.env['muk_ai.session'].create({'name': 'pag-small'})
        for index in range(30):
            session._append_event(
                {
                    'kind': 'text',
                    'content': f'msg-{index}',
                }
            )
        result = session.fetch_events(limit=100)
        self.assertEqual(len(result['events']), 30)
        self.assertFalse(result['has_more_older'])

    def test_clear_session_preserves_event_history(self):
        session = self.env['muk_ai.session'].create({'name': 'clear-trunc'})
        for index in range(120):
            session._append_event(
                {
                    'kind': 'text',
                    'content': f'msg-{index}',
                }
            )
        self.assertEqual(len(session.event_ids), 120)
        session.clear()
        self.assertEqual(len(session.event_ids), 121)
        ordered = session.event_ids.sorted(lambda e: (e.sequence, e.id))
        self.assertEqual(ordered[0].kind, 'text')
        self.assertEqual((ordered[0].payload or {}).get('content'), 'msg-0')
        self.assertEqual(ordered[-1].kind, 'command')
        self.assertEqual((ordered[-1].payload or {}).get('name'), '/clear')
