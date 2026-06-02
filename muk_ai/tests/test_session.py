import json

from datetime import timedelta
from unittest.mock import patch

from odoo import fields
from odoo.exceptions import UserError
from odoo.tests import tagged
from odoo.tools import SQL

from odoo.addons.muk_ai.tools import (
    ADVISORY_LOCK_NAMESPACE,
    MAX_ITERATIONS,
    WORKER_STALE_THRESHOLD,
    format_ui_ctx_tag,
    render_ui_ctx,
)

from odoo.addons.muk_ai.tests.common import AITestCommon


# post_install: creates res.partner, which on Odoo 18 needs sibling modules
# (e.g. account's required res.partner.autopost_bills) fully loaded.
@tagged('post_install', '-at_install')
class TestAiSession(AITestCommon):

    # ----------------------------------------------------------
    # Setup
    # ----------------------------------------------------------

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.session = cls.env['muk_ai.session'].create({'name': 'Test session'})

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    def _patch_provider(self, payloads, captured=None):
        remaining = list(payloads)

        def fake(
            self_arg,
            inputs,
            tools_schema=None,
            text_schema=None,
            on_delta=None,
            model=None,
            **kwargs,
        ):
            if captured is not None:
                captured.append({
                    'tools_schema': tools_schema,
                    'enable_web_search': kwargs.get('enable_web_search', False),
                    'enable_image_generation': kwargs.get('enable_image_generation', False),
                    'enable_code_interpreter': kwargs.get('enable_code_interpreter', False),
                })
            if not remaining:
                raise AssertionError('No more mocked responses')
            return remaining.pop(0)

        return patch.object(
            type(self.provider),
            '_request_responses',
            autospec=True,
            side_effect=fake,
        )

    def _patch_tool_call(self, results_by_name):
        def fake(self_arg, name, arguments, env, enforce_scope):
            if name not in results_by_name:
                raise AssertionError(f'Unexpected tool call: {name}')
            return results_by_name[name], {}, arguments.get('model')

        tool_model = self.env['muk_mcp.tool']
        return patch.object(
            type(tool_model),
            '_execute',
            autospec=True,
            side_effect=fake,
        )

    def _tool_payload(self, name, arguments, call_id='call_1'):
        return {
            'text': '',
            'tool_calls': [{
                'call_id': call_id,
                'name': name,
                'arguments': arguments,
            }],
            'carry_inputs': [{
                'type': 'function_call',
                'name': name,
                'arguments': json.dumps(arguments),
                'call_id': call_id,
            }],
            'usage': {'input_tokens': 4, 'output_tokens': 2},
        }

    def _text_payload(self, text='all done'):
        return {
            'text': text,
            'tool_calls': [],
            'carry_inputs': [{
                'type': 'message',
                'content': [{'type': 'output_text', 'text': text}],
            }],
            'usage': {'input_tokens': 3, 'output_tokens': 1},
        }

    def _extract_ui_ctx(self, inputs):
        for item in inputs or []:
            content = item.get('content') if isinstance(item, dict) else None
            if not isinstance(content, list):
                continue
            for block in content:
                text = isinstance(block, dict) and block.get('text') or ''
                if isinstance(text, str) and text.startswith('<ui_ctx>'):
                    return text
        return None

    def _force_stale_session(self, name='long-tool', state='running'):
        session = self.env['muk_ai.session'].create({'name': name})
        session.write({'state': state})
        session.flush_recordset()
        stale = fields.Datetime.now() - timedelta(seconds=WORKER_STALE_THRESHOLD + 30)
        self.env.cr.execute(SQL(
            "UPDATE muk_ai_session SET write_date = %s, claimed_at = %s "
            "WHERE id = %s",
            stale, stale, session.id,
        ))
        session.invalidate_recordset()
        return session

    def _hold_session_lock(self, session_id):
        class _Holder:
            def __init__(self_, registry):
                self_._cr = registry.cursor()
            def __enter__(self_):
                self_._cr.execute(SQL(
                    "SELECT pg_try_advisory_lock(%s, %s)",
                    ADVISORY_LOCK_NAMESPACE, session_id,
                ))
                acquired = self_._cr.fetchone()[0]
                assert acquired, 'failed to acquire test lock'
                return self_._cr
            def __exit__(self_, *exc):
                try:
                    self_._cr.execute(SQL(
                        "SELECT pg_advisory_unlock(%s, %s)",
                        ADVISORY_LOCK_NAMESPACE, session_id,
                    ))
                    self_._cr.fetchone()
                finally:
                    self_._cr.close()

        return _Holder(self.env.registry)

    # ----------------------------------------------------------
    # Tests: lifecycle
    # ----------------------------------------------------------

    def test_start_text_only_completes(self):
        with self._patch_provider([self._text_payload('hello there')]):
            snapshot = self.session.start('hi')
        self.assertEqual(snapshot['state'], 'done')
        self.assertEqual(snapshot['last_text'], 'hello there')
        self.assertEqual(self.session.iteration_count, 1)
        self.assertEqual(self.session.total_input_tokens, 3)

    def test_start_dispatches_tool_then_completes(self):
        with self._patch_provider([
            self._tool_payload('list_modules', {}, 'call_a'),
            self._text_payload('ok done'),
        ]), self._patch_tool_call({'list_modules': '{"modules": ["base"]}'}):
            snapshot = self.session.start('list installed modules')
        self.assertEqual(snapshot['state'], 'done')
        self.assertEqual(self.session.iteration_count, 2)
        kinds = [entry['kind'] for entry in self.session.fetch_events(limit=500)['events']]
        self.assertIn('tool_call', kinds)
        self.assertIn('tool_result', kinds)

    def test_ask_user_pauses_session(self):
        with self._patch_provider([
            self._tool_payload('ask_user', {'question': 'Which company?'}, 'call_q'),
        ]):
            snapshot = self.session.start('which company')
        self.assertEqual(snapshot['state'], 'waiting')
        pending = self.session.pending_ask or {}
        self.assertEqual(pending.get('kind'), 'question')
        self.assertEqual(pending.get('text'), 'Which company?')

    def test_answer_resumes_session(self):
        with self._patch_provider([
            self._tool_payload('ask_user', {'question': 'Which year?'}, 'call_q'),
        ]):
            self.session.start('pick a year')
        self.assertEqual(self.session.state, 'waiting')
        with self._patch_provider([self._text_payload('Got it: 2026')]):
            snapshot = self.session.answer('2026')
        self.assertEqual(snapshot['state'], 'done')
        self.assertFalse(self.session.pending_ask)

    def test_action_stop_marks_stopped(self):
        self.session.write({'state': 'running'})
        snapshot = self.session.action_stop()
        self.assertEqual(snapshot['state'], 'stopped')

    def test_provider_error_marks_session_error(self):
        def boom(*args, **kwargs):
            raise UserError('provider down')

        with patch.object(
            type(self.provider),
            '_request_responses',
            autospec=True,
            side_effect=boom,
        ):
            snapshot = self.session.start('go')
        self.assertEqual(snapshot['state'], 'error')
        self.assertIn('provider down', self.session.error_message or '')

    def test_max_iterations_marks_error(self):
        payloads = [
            self._tool_payload('list_modules', {}, f'call_{i}')
            for i in range(MAX_ITERATIONS + 1)
        ]
        with self._patch_provider(payloads), self._patch_tool_call({'list_modules': '{}'}):
            snapshot = self.session.start('loop')
        self.assertEqual(snapshot['state'], 'error')
        self.assertIn('Maximum iterations', self.session.error_message or '')

    def test_get_tool_schema_converts_inputschema_to_parameters(self):
        fake_tools = [
            {'name': 't1', 'description': 'first', 'inputSchema': {'type': 'object'}},
            {'name': 't2', 'description': '', 'inputSchema': None},
        ]
        self.session.expanded_tool_names = ['t1', 't2']
        with patch.object(
            type(self.env['muk_mcp.tool']),
            'get_tools',
            autospec=True,
            return_value=fake_tools,
        ):
            schema = self.session._get_tool_schema()
        by_name = {t['name']: t for t in schema}
        self.assertEqual(set(by_name), {'t1', 't2', 'ask_user'})
        self.assertEqual(by_name['t1']['type'], 'function')
        self.assertEqual(by_name['t1']['parameters'], {'type': 'object'})
        self.assertEqual(by_name['t2']['parameters'], {'type': 'object', 'properties': {}})
        self.assertIn('question', by_name['ask_user']['parameters']['properties'])

    def test_bus_event_published_on_state_change(self):
        with patch.object(
            type(self.env['bus.bus']),
            '_sendone',
            autospec=True,
        ) as bus_mock, self._patch_provider([self._text_payload('done')]):
            self.session.start('hi')
        partner = self.session.user_id.partner_id
        targets = [call.args[1] for call in bus_mock.call_args_list]
        self.assertTrue(any(t == partner for t in targets))

    def test_ask_user_skips_sibling_tool_calls(self):
        payload = {
            'text': '',
            'tool_calls': [
                {'call_id': 'write_1', 'name': 'write_record', 'arguments': {'model': 'x'}},
                {'call_id': 'ask_1', 'name': 'ask_user', 'arguments': {'question': 'confirm?'}},
            ],
            'carry_inputs': [],
            'usage': {'input_tokens': 1, 'output_tokens': 1},
        }
        dispatched = []

        def fake_dispatch(self_arg, name, arguments, env, enforce_scope):
            dispatched.append(name)
            return '{"ok": true}', {}, arguments.get('model')

        with self._patch_provider([payload]), patch.object(
            type(self.env['muk_mcp.tool']),
            '_execute',
            autospec=True,
            side_effect=fake_dispatch,
        ):
            snapshot = self.env['muk_ai.session'].create({'name': 'race'}).start('go')
        self.assertEqual(snapshot['state'], 'waiting')
        self.assertNotIn('write_record', dispatched)

    def test_effective_model_uses_agent_override(self):
        model = self.env['muk_ai.model'].create({
            'name': 'Big',
            'provider_id': self.provider.id,
            'technical_name': 'test-big',
            'context_window': 128000,
            'input_rate': 1.0,
            'output_rate': 2.0,
        })
        agent = self.env['muk_ai.agent'].create({
            'name': 'Big',
            'model_id': model.id,
        })
        session = self.env['muk_ai.session'].create({
            'name': 'Big session',
            'agent_id': agent.id,
        })
        self.assertEqual(session._effective_model(), 'test-big')

    def test_effective_model_falls_back_to_global_default(self):
        fallback = self.env['muk_ai.model'].create({
            'name': 'Fallback',
            'provider_id': self.provider.id,
            'technical_name': 'test-fallback',
            'context_window': 128000,
            'input_rate': 1.0,
            'output_rate': 2.0,
        })
        self.provider.default_model_id = fallback.id
        session = self.env['muk_ai.session'].create({'name': 'No override'})
        session.agent_id = False
        self.assertEqual(session._effective_model(), fallback.technical_name)

    def test_terminating_tool_triggers_summary_and_stops(self):
        session = self.env['muk_ai.session'].create({'name': 'terminating'})
        open_view_result = (
            '{"type": "ir.actions.act_window", "res_model": "res.partner"}'
        )
        with self._patch_provider([
            self._tool_payload(
                'open_view', {'model': 'res.partner'}, 'call_v',
            ),
            self._text_payload('Opened the partner list.'),
        ]), self._patch_tool_call({'open_view': open_view_result}):
            snapshot = session.start('show partners')
        self.assertEqual(snapshot['state'], 'done')
        self.assertEqual(session.iteration_count, 2)
        self.assertIn('Opened the partner list', session.last_text or '')

    def test_terminating_tool_skips_sibling_tool_calls(self):
        payload = {
            'text': '',
            'tool_calls': [
                {'call_id': 'open_1', 'name': 'open_view', 'arguments': {'model': 'res.partner'}},
                {'call_id': 'extra_1', 'name': 'list_modules', 'arguments': {}},
            ],
            'carry_inputs': [],
            'usage': {'input_tokens': 1, 'output_tokens': 1},
        }
        dispatched = []

        def recorder(self_arg, name, arguments, env, enforce_scope):
            dispatched.append(name)
            if name == 'open_view':
                return (
                    '{"type": "ir.actions.act_window", "res_model": "res.partner"}',
                    {},
                    arguments.get('model'),
                )
            return '{}', {}, arguments.get('model')

        with self._patch_provider([payload, self._text_payload('Done.')]), patch.object(
            type(self.env['muk_mcp.tool']),
            '_execute',
            autospec=True,
            side_effect=recorder,
        ):
            snapshot = self.env['muk_ai.session'].create({'name': 'skip'}).start('go')
        self.assertEqual(snapshot['state'], 'done')
        self.assertEqual(dispatched, ['open_view'])

    def test_agent_capability_flags_forwarded_to_provider(self):
        agent = self.env['muk_ai.agent'].create({
            'name': 'Power',
            'enable_web_search': True,
            'enable_image_generation': True,
            'enable_code_interpreter': True,
        })
        session = self.env['muk_ai.session'].create({
            'name': 'Power session',
            'agent_id': agent.id,
        })
        captured = []
        with self._patch_provider([self._text_payload('ok')], captured=captured):
            session.start('go')
        self.assertTrue(captured)
        self.assertTrue(captured[0]['enable_web_search'])
        self.assertTrue(captured[0]['enable_image_generation'])
        self.assertTrue(captured[0]['enable_code_interpreter'])

    def test_agent_capability_flags_default_off(self):
        agent = self.env['muk_ai.agent'].create({'name': 'Plain'})
        session = self.env['muk_ai.session'].create({
            'name': 'default flags',
            'agent_id': agent.id,
        })
        captured = []
        with self._patch_provider([self._text_payload('ok')], captured=captured):
            session.start('go')
        self.assertTrue(captured)
        self.assertFalse(captured[0]['enable_web_search'])
        self.assertFalse(captured[0]['enable_image_generation'])
        self.assertFalse(captured[0]['enable_code_interpreter'])

    # ----------------------------------------------------------
    # Tests: tokens and cost
    # ----------------------------------------------------------

    def test_last_input_tokens_tracks_most_recent_turn(self):
        session = self.env['muk_ai.session'].create({'name': 'token meter'})

        def make_payload(tokens):
            return {
                'text': 'ok',
                'tool_calls': [],
                'carry_inputs': [],
                'usage': {'input_tokens': tokens, 'output_tokens': 1},
            }

        with self._patch_provider([make_payload(42)]):
            session.start('hi')
        self.assertEqual(session.last_input_tokens, 42)
        self.assertEqual(session.total_input_tokens, 42)
        with self._patch_provider([make_payload(120)]):
            session.send_message('again')
        self.assertEqual(session.last_input_tokens, 120)
        self.assertEqual(session.total_input_tokens, 162)

    def test_snapshot_exposes_context_window(self):
        model = self.env['muk_ai.model'].create({
            'name': 'Bounded',
            'provider_id': self.provider.id,
            'technical_name': 'test-bounded',
            'context_window': 50000,
            'input_rate': 1.0,
            'output_rate': 2.0,
        })
        agent = self.env['muk_ai.agent'].create({
            'name': 'Bounded',
            'model_id': model.id,
        })
        session = self.env['muk_ai.session'].create({
            'name': 'with agent',
            'agent_id': agent.id,
        })
        snapshot = session.get_snapshot()
        self.assertEqual(snapshot['context_window'], 50000)
        self.assertEqual(snapshot['last_input_tokens'], 0)

    # ----------------------------------------------------------
    # Tests: clear and compact
    # ----------------------------------------------------------

    def test_clear_resets_conversation(self):
        session = self.env['muk_ai.session'].create({'name': 'clearable'})
        with self._patch_provider([self._text_payload('hi')]):
            session.start('hello')
        self.assertEqual(session.state, 'done')
        self.assertTrue(session.conversation)
        events_before = session.fetch_events(limit=500)['events']
        self.assertTrue(events_before)
        snapshot = session.clear()
        self.assertEqual(snapshot['state'], 'new')
        self.assertEqual(snapshot['iteration_count'], 0)
        self.assertEqual(snapshot['last_input_tokens'], 0)
        self.assertFalse(session.conversation)
        self.assertTrue(session.cleared_at)
        unified = session.fetch_events(limit=500)['events']
        self.assertEqual(
            len(unified), len(events_before) + 1,
            "clear() must preserve prior events and append exactly one /clear marker",
        )
        self.assertEqual(unified[-1].get('kind'), 'command')
        self.assertEqual(unified[-1].get('name'), '/clear')

    def test_clear_refuses_running(self):
        session = self.env['muk_ai.session'].create({'name': 'running'})
        session.state = 'running'
        with self.assertRaises(UserError):
            session.clear()

    def _seed_large_conversation(self, session, pairs=10, chunk_chars=10000):
        if not session.conversation:
            with self._patch_provider([self._text_payload('seed reply')]):
                session.start('seed user message')
        big = 'x' * chunk_chars
        bulky = list(session.conversation or [])
        for index in range(pairs):
            bulky.append({
                'role': 'user',
                'content': [{'type': 'input_text', 'text': f'user-{index} {big}'}],
            })
            bulky.append({
                'type': 'message',
                'role': 'assistant',
                'content': [{'type': 'output_text', 'text': f'assistant-{index} {big}'}],
            })
        session.conversation = bulky

    def test_compact_replaces_conversation_with_summary(self):
        session = self.env['muk_ai.session'].create({'name': 'compactable'})
        self._seed_large_conversation(session)
        self.assertEqual(session.state, 'done')
        pre_len = len(session.conversation)
        summary_payload = {
            'text': 'User asked for help. Assistant replied.',
            'tool_calls': [],
            'carry_inputs': [],
            'usage': {'input_tokens': 0, 'output_tokens': 0},
        }
        with self._patch_provider([summary_payload]):
            snapshot = session.compact()
        self.assertGreaterEqual(len(session.conversation), 2)
        self.assertLess(len(session.conversation), pre_len + 1)
        self.assertEqual(session.last_input_tokens, 0)
        self.assertEqual(snapshot['last_input_tokens'], 0)
        unified = session.fetch_events(limit=500)['events']
        last_entry = unified[-1]
        self.assertEqual(last_entry.get('kind'), 'compact_progress')
        self.assertEqual(last_entry.get('name'), '/compact')
        self.assertEqual(last_entry.get('state'), 'done')
        self.assertFalse(last_entry.get('auto'))
        self.assertIn('summary', last_entry)

    def test_compact_refuses_empty(self):
        session = self.env['muk_ai.session'].create({'name': 'empty'})
        with self.assertRaises(UserError):
            session.compact()

    def test_compact_preserves_recent_tail(self):
        session = self.env['muk_ai.session'].create({'name': 'tail-keep'})
        self._seed_large_conversation(session, pairs=12, chunk_chars=12000)
        last_assistant_text = (
            session.conversation[-1]['content'][0]['text']
        )
        last_user_text = (
            session.conversation[-2]['content'][0]['text']
        )
        with self._patch_provider([self._text_payload('compact summary')]):
            session.compact()
        tail_texts = []
        for entry in session.conversation:
            for block in entry.get('content') or []:
                text = block.get('text') if isinstance(block, dict) else None
                if isinstance(text, str):
                    tail_texts.append(text)
        joined = '\n'.join(tail_texts)
        self.assertIn(last_assistant_text, joined)
        self.assertIn(last_user_text, joined)

    def test_compact_uses_anchored_update_when_prior_summary_exists(self):
        session = self.env['muk_ai.session'].create({'name': 'anchored'})
        self._seed_large_conversation(session, pairs=10, chunk_chars=10000)
        captured = []
        with self._patch_provider(
            [self._text_payload('first summary text')], captured=captured,
        ):
            session.compact()
        self.assertTrue(captured)
        self._seed_large_conversation(session, pairs=10, chunk_chars=10000)
        captured_second = []

        def fake(
            self_arg,
            inputs,
            tools_schema=None,
            text_schema=None,
            on_delta=None,
            model=None,
            **kwargs,
        ):
            captured_second.append(list(inputs or []))
            return self._text_payload('second summary text')

        with patch.object(
            type(self.provider),
            '_request_responses',
            autospec=True,
            side_effect=fake,
        ):
            session.compact()
        self.assertTrue(captured_second)
        last_user_text = ''
        for block in (captured_second[0][-1].get('content') or []):
            if isinstance(block, dict) and isinstance(block.get('text'), str):
                last_user_text = block['text']
                break
        self.assertIn('<previous-summary>', last_user_text)

    def test_compact_keeps_event_log(self):
        session = self.env['muk_ai.session'].create({'name': 'eventlog'})
        self._seed_large_conversation(session)
        events_before = session.fetch_events(limit=500)['events']
        self.assertTrue(events_before)
        with self._patch_provider([self._text_payload('summary 123')]):
            session.compact()
        events_after = session.fetch_events(limit=500)['events']
        self.assertGreaterEqual(len(events_after), len(events_before))
        kinds = [event.get('kind') for event in events_after]
        names = [event.get('name') for event in events_after]
        self.assertIn('compact_progress', kinds)
        self.assertIn('/compact', names)

    def test_compact_includes_available_tools_block(self):
        session = self.env['muk_ai.session'].create({'name': 'tools-block'})
        self._seed_large_conversation(session)
        with self._patch_provider([self._text_payload('compact summary')]):
            session.compact()
        first = session.conversation[0]
        text = first.get('content', [{}])[0].get('text', '')
        self.assertIn('<available_tools>', text)

    def test_compact_accrues_cost(self):
        session = self.env['muk_ai.session'].create({'name': 'cost-accrue'})
        self._seed_large_conversation(session)
        before_input_cost = session.total_input_cost or 0.0
        before_input_tokens = session.total_input_tokens
        summary_payload = {
            'text': 'summary text',
            'tool_calls': [],
            'carry_inputs': [],
            'usage': {'input_tokens': 1234, 'output_tokens': 56},
        }
        with self._patch_provider([summary_payload]):
            session.compact()
        self.assertGreater(session.total_input_tokens, before_input_tokens)
        self.assertGreaterEqual(
            session.total_input_cost or 0.0, before_input_cost,
        )

    def test_compact_empty_summary_rollback(self):
        session = self.env['muk_ai.session'].create({'name': 'empty-summary'})
        self._seed_large_conversation(session)
        original_conv = list(session.conversation)
        empty_payload = {
            'text': '',
            'tool_calls': [],
            'carry_inputs': [],
            'usage': {'input_tokens': 1, 'output_tokens': 0},
        }
        with self._patch_provider([empty_payload]):
            session.compact()
        self.assertEqual(session.state, 'done')
        self.assertEqual(list(session.conversation), original_conv)

    # ----------------------------------------------------------
    # Tests: view context
    # ----------------------------------------------------------

    def test_view_context_injected_into_inputs(self):
        session = self.env['muk_ai.session'].create({'name': 'ctx'})
        session.view_context = {
            'kind': 'record',
            'model': 'res.partner',
            'id': 42,
            'display_name': 'ACME Corp',
        }
        captured = []

        def fake(
            self_arg,
            inputs,
            tools_schema=None,
            text_schema=None,
            on_delta=None,
            model=None,
            **kwargs,
        ):
            captured.append(list(inputs or []))
            return self._text_payload('ok')

        with patch.object(
            type(self.provider),
            '_request_responses',
            autospec=True,
            side_effect=fake,
        ):
            session.start('what is the total')
        self.assertTrue(captured)
        tag = self._extract_ui_ctx(captured[0])
        self.assertIsNotNone(tag)
        self.assertIn('res.partner/42', tag)
        self.assertIn('"ACME Corp"', tag)

    def test_view_context_not_persisted_in_conversation(self):
        session = self.env['muk_ai.session'].create({'name': 'nopersist'})
        session.view_context = {
            'kind': 'record',
            'model': 'res.partner',
            'id': 7,
            'display_name': 'Joe',
        }
        with self._patch_provider([self._text_payload('hi')]):
            session.start('hello')
        tag_entries = [
            entry for entry in session.conversation or []
            if isinstance(entry.get('content'), list)
            and any(
                isinstance(block, dict)
                and isinstance(block.get('text'), str)
                and block['text'].startswith('<ui_ctx>')
                for block in entry['content']
            )
        ]
        self.assertEqual(tag_entries, [])

    def test_view_context_updates_on_open_record_tool(self):
        session = self.env['muk_ai.session'].create({'name': 'open-record'})
        partner = self.env['res.partner'].create({'name': 'ViewCtx Partner'})
        open_record_result = (
            '{"type": "ir.actions.act_window", "res_model": "res.partner", '
            f'"res_id": {partner.id}, "view_mode": "form", '
            '"views": [[false, "form"]], "target": "current"}'
        )
        with self._patch_provider([
            self._tool_payload(
                'open_record', {'model': 'res.partner', 'res_id': partner.id},
                'call_or',
            ),
            self._text_payload('Opened partner.'),
        ]), self._patch_tool_call({'open_record': open_record_result}):
            session.start('show ViewCtx Partner')
        self.assertEqual(session.state, 'done')
        self.assertIsInstance(session.view_context, dict)
        self.assertEqual(session.view_context.get('kind'), 'record')
        self.assertEqual(session.view_context.get('model'), 'res.partner')
        self.assertEqual(session.view_context.get('id'), partner.id)
        self.assertEqual(session.view_context.get('display_name'), 'ViewCtx Partner')

    def test_view_context_updates_on_open_view_tool(self):
        session = self.env['muk_ai.session'].create({'name': 'open-view'})
        open_view_result = (
            '{"type": "ir.actions.act_window", "res_model": "res.partner", '
            '"view_mode": "list", "views": [[false, "list"]], '
            '"domain": [["is_company", "=", true]], "target": "current"}'
        )
        with self._patch_provider([
            self._tool_payload(
                'open_view', {'model': 'res.partner'}, 'call_ov',
            ),
            self._text_payload('Opened the list.'),
        ]), self._patch_tool_call({'open_view': open_view_result}):
            session.start('show companies')
        self.assertEqual(session.state, 'done')
        self.assertIsInstance(session.view_context, dict)
        self.assertEqual(session.view_context.get('kind'), 'list')
        self.assertEqual(session.view_context.get('model'), 'res.partner')
        self.assertEqual(session.view_context.get('view_type'), 'list')
        self.assertEqual(
            session.view_context.get('domain'),
            [['is_company', '=', True]],
        )

    def test_set_view_context_record(self):
        session = self.env['muk_ai.session'].create({'name': 'set'})
        snapshot = session.set_view_context({
            'kind': 'record',
            'model': 'res.partner',
            'id': 99,
            'display_name': 'Demo',
        })
        self.assertEqual(session.view_context.get('id'), 99)
        self.assertEqual(snapshot['view_context']['model'], 'res.partner')

    def test_set_view_context_clears_on_none(self):
        session = self.env['muk_ai.session'].create({'name': 'clear-ctx'})
        session.view_context = {
            'kind': 'record', 'model': 'res.partner', 'id': 3,
        }
        session.set_view_context(None)
        self.assertFalse(session.view_context)
        session.view_context = {'kind': 'list', 'model': 'res.partner'}
        session.set_view_context({'kind': 'none'})
        self.assertFalse(session.view_context)

    def test_set_view_context_rejects_bad_payload(self):
        session = self.env['muk_ai.session'].create({'name': 'bad'})
        with self.assertRaises(UserError):
            session.set_view_context({'kind': 'banana'})
        with self.assertRaises(UserError):
            session.set_view_context({'kind': 'record', 'model': 'm', 'id': -1})

    def test_unpin_view_context(self):
        session = self.env['muk_ai.session'].create({'name': 'unpin'})
        session.view_context = {
            'kind': 'record', 'model': 'res.partner', 'id': 3,
        }
        snapshot = session.unpin_view_context()
        self.assertFalse(session.view_context)
        self.assertIsNone(snapshot['view_context'])
        unified = session.fetch_events(limit=500)['events']
        last_entry = unified[-1] if unified else {}
        self.assertEqual(last_entry.get('kind'), 'command')
        self.assertEqual(last_entry.get('name'), '/unpin')

    def test_snapshot_exposes_view_context(self):
        session = self.env['muk_ai.session'].create({'name': 'snap'})
        session.view_context = {
            'kind': 'record', 'model': 'res.partner', 'id': 5,
            'display_name': 'Who',
        }
        snapshot = session.get_snapshot()
        self.assertEqual(snapshot['view_context']['model'], 'res.partner')
        self.assertEqual(snapshot['view_context']['id'], 5)

    def test_render_ui_ctx_returns_none_when_empty(self):
        self.assertIsNone(render_ui_ctx(None))
        self.assertIsNone(render_ui_ctx({}))
        self.assertIsNone(format_ui_ctx_tag({}))

    def test_render_ui_ctx_formats_list(self):
        tag = format_ui_ctx_tag({
            'kind': 'list',
            'model': 'sale.order',
            'view_type': 'kanban',
            'domain': [['state', '=', 'sale']],
        })
        self.assertTrue(tag.startswith('<ui_ctx>'))
        self.assertIn('sale.order', tag)
        self.assertIn('kanban', tag)
        self.assertIn('domain=', tag)

    # ----------------------------------------------------------
    # Tests: regenerate
    # ----------------------------------------------------------

    def test_regenerate_last_turn_rewinds_and_replays(self):
        session = self.env['muk_ai.session'].create({'name': 'rewind'})
        with self._patch_provider([self._text_payload('first answer')]):
            session.start('what is 2+2?')
        self.assertEqual(session.state, 'done')
        original_log = list(session.fetch_events(limit=500)['events'])
        original_conv = list(session.conversation or [])
        with self._patch_provider([self._text_payload('four')]):
            snapshot = session.regenerate_last_turn()
        self.assertEqual(snapshot['state'], 'done')
        self.assertIn('four', session.last_text or '')
        kinds = [entry.get('kind') for entry in session.fetch_events(limit=500)['events']]
        self.assertEqual(kinds[-2:], ['user_message', 'text'])
        self.assertLessEqual(len(session.conversation or []), len(original_conv))
        self.assertGreater(len(original_log), 0)

    def test_regenerate_refuses_while_running(self):
        session = self.env['muk_ai.session'].create({'name': 'running'})
        session.write({'state': 'running'})
        with self.assertRaises(UserError):
            session.regenerate_last_turn()

    def test_regenerate_without_user_turn_raises(self):
        session = self.env['muk_ai.session'].create({'name': 'empty'})
        with self.assertRaises(UserError):
            session.regenerate_last_turn()

    # ----------------------------------------------------------
    # Tests: undo / fork
    # ----------------------------------------------------------

    def test_undo_to_event_truncates_log_and_conversation(self):
        session = self.env['muk_ai.session'].create({'name': 'rewindable'})
        with self._patch_provider([self._text_payload('answer 1')]):
            session.start('question 1')
        with self._patch_provider([self._text_payload('answer 2')]):
            session.send_message('question 2')
        with self._patch_provider([self._text_payload('answer 3')]):
            session.send_message('question 3')
        events = session.event_ids.sorted('sequence')
        second_user = next(
            event for event in events
            if event.kind == 'user_message'
            and 'question 2' in (event.payload or {}).get('content', '')
        )
        before_pairs = sum(
            1 for entry in (session.conversation or [])
            if isinstance(entry, dict) and entry.get('role') == 'user'
        )
        self.assertEqual(before_pairs, 3)
        snapshot = session.undo_to_event(second_user.id)
        self.assertEqual(snapshot['state'], 'done')
        kept_users = [
            entry for entry in (session.conversation or [])
            if isinstance(entry, dict) and entry.get('role') == 'user'
        ]
        self.assertEqual(len(kept_users), 1)
        kinds = [event.kind for event in session.event_ids.sorted('sequence')]
        self.assertNotIn('tool_call', kinds)
        self.assertEqual(kinds.count('user_message'), 1)
        self.assertEqual(kinds.count('text'), 1)

    def test_undo_to_event_refuses_while_running(self):
        session = self.env['muk_ai.session'].create({'name': 'running'})
        with self._patch_provider([self._text_payload('answer')]):
            session.start('question')
        target = session.event_ids.sorted('sequence')[0]
        session.write({'state': 'running'})
        with self.assertRaises(UserError):
            session.undo_to_event(target.id)

    def test_undo_to_event_on_assistant_keeps_preceding_user(self):
        session = self.env['muk_ai.session'].create({'name': 'rewind-asst'})
        with self._patch_provider([self._text_payload('answer 1')]):
            session.start('question 1')
        with self._patch_provider([self._text_payload('answer 2')]):
            session.send_message('question 2')
        events = session.event_ids.sorted('sequence')
        last_text = next(
            event for event in reversed(events)
            if event.kind == 'text'
        )
        session.undo_to_event(last_text.id)
        users = [
            entry for entry in (session.conversation or [])
            if isinstance(entry, dict) and entry.get('role') == 'user'
        ]
        self.assertEqual(len(users), 2)
        self.assertEqual(
            session.event_ids.sorted('sequence')[-1].kind, 'user_message',
        )

    def test_fork_at_event_creates_independent_session(self):
        session = self.env['muk_ai.session'].create({'name': 'forkable'})
        with self._patch_provider([self._text_payload('answer 1')]):
            session.start('question 1')
        with self._patch_provider([self._text_payload('answer 2')]):
            session.send_message('question 2')
        events = session.event_ids.sorted('sequence')
        second_user = next(
            event for event in events
            if event.kind == 'user_message'
            and 'question 2' in (event.payload or {}).get('content', '')
        )
        fork_id = session.fork_at_event(second_user.id)
        fork = self.env['muk_ai.session'].browse(fork_id)
        self.assertTrue(fork.exists())
        self.assertNotEqual(fork.id, session.id)
        self.assertIn('(fork)', fork.name)
        fork_users = [
            entry for entry in (fork.conversation or [])
            if isinstance(entry, dict) and entry.get('role') == 'user'
        ]
        self.assertEqual(
            len(fork_users), 2,
            "fork keeps the clicked user message in the new session",
        )
        fork_kinds = [event.kind for event in fork.event_ids.sorted('sequence')]
        self.assertEqual(fork_kinds[-1], 'user_message')
        original_users = [
            entry for entry in (session.conversation or [])
            if isinstance(entry, dict) and entry.get('role') == 'user'
        ]
        self.assertEqual(len(original_users), 2)
        self.assertEqual(fork.state, 'done')

    def test_fork_at_event_preserves_agent(self):
        agent = self.env['muk_ai.agent']._get_default()
        session = self.env['muk_ai.session'].create({
            'name': 'fork-agent', 'agent_id': agent.id,
        })
        with self._patch_provider([self._text_payload('answer 1')]):
            session.start('question 1')
        with self._patch_provider([self._text_payload('answer 2')]):
            session.send_message('question 2')
        target = next(
            event for event in session.event_ids.sorted('sequence')
            if event.kind == 'user_message'
            and 'question 2' in (event.payload or {}).get('content', '')
        )
        fork_id = session.fork_at_event(target.id)
        fork = self.env['muk_ai.session'].browse(fork_id)
        self.assertEqual(fork.agent_id, agent)

    def test_fork_refuses_while_running(self):
        session = self.env['muk_ai.session'].create({'name': 'running-fork'})
        with self._patch_provider([self._text_payload('answer')]):
            session.start('question')
        target = session.event_ids.sorted('sequence')[0]
        session.write({'state': 'running'})
        with self.assertRaises(UserError):
            session.fork_at_event(target.id)

    def test_compact_tail_drop_fallback_on_provider_error(self):
        session = self.env['muk_ai.session'].create({'name': 'tail-drop'})
        self._seed_large_conversation(session, pairs=8, chunk_chars=8000)
        pre_len = len(session.conversation)

        def boom(*args, **kwargs):
            raise RuntimeError("context_length_exceeded: too big")

        with patch.object(
            type(self.provider),
            '_request_responses',
            autospec=True,
            side_effect=boom,
        ):
            session.compact()
        self.assertEqual(
            session.state, 'done',
            "tail-drop fallback should land in 'done', not 'error'",
        )
        self.assertLess(
            len(session.conversation), pre_len,
            "fallback must drop oldest entries",
        )
        events = session.fetch_events(limit=500)['events']
        last = events[-1]
        self.assertEqual(last.get('kind'), 'compact_progress')
        self.assertEqual(last.get('state'), 'done')
        self.assertEqual(last.get('fallback'), 'tail_drop')
        self.assertIn('dropped', (last.get('summary') or '').lower())

    # ----------------------------------------------------------
    # Tests: attachments
    # ----------------------------------------------------------

    def test_upload_attachments_creates_and_links(self):
        session = self.env['muk_ai.session'].create({'name': 'upload'})
        descriptors = session.upload_attachments([{
            'filename': 'note.txt',
            'mimetype': 'text/plain',
            'data_b64': 'aGVsbG8=',
        }])
        self.assertEqual(len(descriptors), 1)
        self.assertEqual(descriptors[0]['filename'], 'note.txt')
        self.assertTrue(session.attachment_ids)
        attachment = session.attachment_ids[0]
        self.assertEqual(attachment.name, 'note.txt')

    def test_discard_attachments_unlinks_orphans(self):
        session = self.env['muk_ai.session'].create({'name': 'discard'})
        session.upload_attachments([{
            'filename': 'a.txt', 'mimetype': 'text/plain',
            'data_b64': 'YQ==',
        }])
        attachment = session.attachment_ids[0]
        attachment_id = attachment.id
        session.discard_attachments([attachment_id])
        self.assertFalse(
            self.env['ir.attachment'].browse(attachment_id).exists()
        )

    # ----------------------------------------------------------
    # Tests: view context cleaners
    # ----------------------------------------------------------

    def test_set_view_context_list_with_domain(self):
        session = self.env['muk_ai.session'].create({'name': 'ctx-list'})
        session.set_view_context({
            'kind': 'list', 'model': 'sale.order', 'view_type': 'kanban',
            'domain': [['state', '=', 'sale']],
        })
        self.assertEqual(session.view_context['kind'], 'list')
        self.assertEqual(session.view_context['view_type'], 'kanban')
        self.assertEqual(session.view_context['domain'], [['state', '=', 'sale']])

    def test_set_view_context_action(self):
        session = self.env['muk_ai.session'].create({'name': 'ctx-action'})
        session.set_view_context({
            'kind': 'action', 'model': 'sale.order', 'action_id': 42,
        })
        self.assertEqual(session.view_context['kind'], 'action')
        self.assertEqual(session.view_context['action_id'], 42)

    def test_set_view_context_pivot_with_measures(self):
        session = self.env['muk_ai.session'].create({'name': 'ctx-pivot'})
        session.set_view_context({
            'kind': 'pivot', 'model': 'sale.order',
            'pivot_measures': ['amount_total'],
            'pivot_row_groupby': ['partner_id'],
            'pivot_column_groupby': ['user_id'],
            'domain': [['state', '=', 'sale']],
        })
        self.assertEqual(session.view_context['view_type'], 'pivot')
        self.assertEqual(session.view_context['pivot_measures'], ['amount_total'])
        self.assertEqual(session.view_context['pivot_row_groupby'], ['partner_id'])
        self.assertEqual(session.view_context['domain'], [['state', '=', 'sale']])

    def test_set_view_context_graph(self):
        session = self.env['muk_ai.session'].create({'name': 'ctx-graph'})
        session.set_view_context({
            'kind': 'graph', 'model': 'sale.order',
            'graph_mode': 'bar', 'graph_measure': 'amount_total',
            'graph_groupbys': ['partner_id'],
        })
        self.assertEqual(session.view_context['view_type'], 'graph')
        self.assertEqual(session.view_context['graph_mode'], 'bar')
        self.assertEqual(session.view_context['graph_measure'], 'amount_total')
        self.assertEqual(session.view_context['graph_groupbys'], ['partner_id'])

    def test_set_view_context_rejects_non_string_model(self):
        session = self.env['muk_ai.session'].create({'name': 'ctx-bad-model'})
        with self.assertRaises(UserError):
            session.set_view_context({
                'kind': 'list', 'model': 42,
            })

    def test_set_view_context_rejects_non_list_domain(self):
        session = self.env['muk_ai.session'].create({'name': 'ctx-bad-domain'})
        with self.assertRaises(UserError):
            session.set_view_context({
                'kind': 'list', 'model': 'res.partner', 'domain': 'oops',
            })

    def test_set_view_context_rejects_non_list_pivot_fields(self):
        session = self.env['muk_ai.session'].create({'name': 'ctx-pivot-bad'})
        with self.assertRaises(UserError):
            session.set_view_context({
                'kind': 'pivot', 'model': 'sale.order',
                'pivot_measures': 'oops',
            })

    def test_set_view_context_rejects_non_list_graph_groupbys(self):
        session = self.env['muk_ai.session'].create({'name': 'ctx-graph-bad'})
        with self.assertRaises(UserError):
            session.set_view_context({
                'kind': 'graph', 'model': 'sale.order',
                'graph_groupbys': 'oops',
            })

    def test_set_view_context_rejects_non_string_graph_mode(self):
        session = self.env['muk_ai.session'].create({'name': 'ctx-graph-mode'})
        with self.assertRaises(UserError):
            session.set_view_context({
                'kind': 'graph', 'model': 'sale.order', 'graph_mode': 123,
            })

    # ----------------------------------------------------------
    # Tests: approval mode toggle
    # ----------------------------------------------------------

    def test_set_approval_mode_accepts_ask(self):
        session = self.env['muk_ai.session'].create({'name': 'mode'})
        session.set_approval_mode('ask')
        self.assertEqual(session.override_approval_mode, 'ask')

    def test_set_approval_mode_clears_on_empty(self):
        session = self.env['muk_ai.session'].create({'name': 'clear-mode'})
        session.set_approval_mode('off')
        session.set_approval_mode(None)
        self.assertFalse(session.override_approval_mode)

    def test_set_approval_mode_rejects_unknown(self):
        session = self.env['muk_ai.session'].create({'name': 'mode-bad'})
        with self.assertRaises(UserError):
            session.set_approval_mode('banana')

    # ----------------------------------------------------------
    # Tests: send_message routing
    # ----------------------------------------------------------

    def test_send_message_routes_first_turn_to_start(self):
        session = self.env['muk_ai.session'].create({'name': 'new'})
        with self._patch_provider([self._text_payload('hello')]):
            snapshot = session.send_message('hi')
        self.assertEqual(snapshot['state'], 'done')
        self.assertEqual(session.iteration_count, 1)

    def test_send_message_routes_pending_question_to_answer(self):
        session = self.env['muk_ai.session'].create({'name': 'pending'})
        with self._patch_provider([
            self._tool_payload('ask_user', {'question': 'Which year?'}, 'call_q'),
        ]):
            session.start('pick a year')
        self.assertEqual(session.state, 'waiting')
        with self._patch_provider([self._text_payload('2026')]):
            snapshot = session.send_message('2026')
        self.assertEqual(snapshot['state'], 'done')

    def test_send_message_queues_while_running(self):
        session = self.env['muk_ai.session'].create({'name': 'running'})
        session.write({'state': 'running'})
        snapshot = session.send_message('queued while running')
        self.assertEqual(session.state, 'running')
        self.assertEqual(len(session.pending_ids), 1)
        self.assertEqual(
            session.pending_ids[0].content, 'queued while running',
        )
        self.assertEqual(
            snapshot['pending_user_messages'][0]['content'],
            'queued while running',
        )

    # ----------------------------------------------------------
    # Tests: worker recovery
    # ----------------------------------------------------------

    def test_recover_if_stuck_skips_when_advisory_lock_is_held(self):
        session = self._force_stale_session('long-tool')
        with self._hold_session_lock(session.id):
            self.assertFalse(session._recover_if_stuck())
            session.invalidate_recordset()
            self.assertEqual(session.state, 'running')

    def test_recover_if_stuck_flips_to_error_when_lock_is_free(self):
        session = self._force_stale_session('dead-worker')
        self.assertTrue(session._recover_if_stuck())
        session.invalidate_recordset()
        self.assertEqual(session.state, 'error')

    def test_recover_if_stuck_noop_for_fresh_session(self):
        session = self.env['muk_ai.session'].create({'name': 'fresh'})
        session.write({'state': 'running'})
        self.assertFalse(session._recover_if_stuck())
        session.invalidate_recordset()
        self.assertEqual(session.state, 'running')

    def test_recover_if_stuck_drops_pending_queue(self):
        session = self._force_stale_session('queued-while-stuck')
        self.env['muk_ai.session.pending'].create({
            'session_id': session.id,
            'content': 'queued before sweep',
        })
        self.assertEqual(len(session.pending_ids), 1)
        self.assertTrue(session._recover_if_stuck())
        session.invalidate_recordset()
        self.assertEqual(session.state, 'error')
        self.assertEqual(len(session.pending_ids), 0)

    def test_sweep_orphan_skips_session_with_held_lock(self):
        session = self._force_stale_session('busy-worker')
        with self._hold_session_lock(session.id):
            self.env['muk_ai.session']._sweep_orphan_sessions()
            session.invalidate_recordset()
            self.assertEqual(session.state, 'running')

    def test_sweep_orphan_flips_session_when_lock_is_free(self):
        session = self._force_stale_session('truly-orphaned')
        self.env['muk_ai.session']._sweep_orphan_sessions()
        session.invalidate_recordset()
        self.assertEqual(session.state, 'error')

    def test_sweep_orphan_skips_fresh_session_with_recent_write_date(self):
        session = self.env['muk_ai.session'].create({'name': 'just-started'})
        session.write({'state': 'running'})
        self.env['muk_ai.session']._sweep_orphan_sessions()
        session.invalidate_recordset()
        self.assertEqual(session.state, 'running')

    def test_sweep_orphan_skips_session_with_recent_heartbeat(self):
        session = self.env['muk_ai.session'].create({'name': 'live-heartbeat'})
        session.write({
            'state': 'running',
            'claimed_at': fields.Datetime.now(),
        })
        self.env['muk_ai.session']._sweep_orphan_sessions()
        session.invalidate_recordset()
        self.assertEqual(session.state, 'running')

    def test_sweep_orphan_keeps_compacting_session_with_held_lock(self):
        session = self._force_stale_session('compacting', state='compacting')
        with self._hold_session_lock(session.id):
            self.env['muk_ai.session']._sweep_orphan_sessions()
            session.invalidate_recordset()
            self.assertEqual(session.state, 'compacting')

    def test_heartbeat_claim_bumps_claimed_at(self):
        session = self.env['muk_ai.session'].create({'name': 'beating'})
        old = fields.Datetime.now() - timedelta(seconds=120)
        session.write({'state': 'running', 'claimed_at': old})
        session._heartbeat_claim()
        session.invalidate_recordset()
        self.assertGreater(session.claimed_at, old)

    # ----------------------------------------------------------
    # Tests: long-tool concurrent recovery
    # ----------------------------------------------------------

    def test_pdf_ocr_long_tool_call_survives_orphan_sweep(self):
        session = self._force_stale_session('pdf-ocr')
        with self._hold_session_lock(session.id):
            self.env['muk_ai.session']._sweep_orphan_sessions()
            session.invalidate_recordset()
            self.assertEqual(session.state, 'running',
                'live worker mid-tool must NOT be killed by the orphan sweep')
            snapshot = session.send_message('done?')
            session.invalidate_recordset()
            self.assertEqual(session.state, 'running',
                'live worker mid-tool must NOT be killed by send_message recovery')
            self.assertEqual(len(session.pending_ids), 1,
                'follow-up message should queue, not abort the run')
            self.assertEqual(
                snapshot['pending_user_messages'][0]['content'], 'done?',
            )

    def test_pdf_ocr_session_recovers_after_worker_death(self):
        session = self._force_stale_session('crashed-worker')
        self.env['muk_ai.session']._sweep_orphan_sessions()
        session.invalidate_recordset()
        self.assertEqual(session.state, 'error')
        self.assertIn('abandoned', session.error_message)

    def test_commit_safe_retries_on_serialization_failure(self):
        from unittest.mock import MagicMock

        from psycopg2.errors import SerializationFailure

        from odoo.addons.muk_ai.models import session as session_module

        attempts = {'commit': 0}

        def fake_commit():
            attempts['commit'] += 1
            if attempts['commit'] == 1:
                raise SerializationFailure('simulated concurrent update')

        fake_cr = MagicMock(commit=fake_commit, rollback=MagicMock())
        fake_env = MagicMock(cr=fake_cr)
        fake_session = MagicMock(env=fake_env, id=1)

        with (
            patch.object(session_module.modules.module, 'current_test', False),
            patch.object(session_module.time, 'sleep'),
        ):
            session_module.AISession._commit_safe(fake_session)

        self.assertEqual(attempts['commit'], 2)
        self.assertEqual(fake_cr.rollback.call_count, 1)

    def test_commit_safe_gives_up_after_max_retries(self):
        from unittest.mock import MagicMock

        from psycopg2.errors import SerializationFailure

        from odoo.addons.muk_ai.models import session as session_module

        attempts = {'commit': 0}

        def fake_commit():
            attempts['commit'] += 1
            raise SerializationFailure('simulated persistent contention')

        fake_cr = MagicMock(commit=fake_commit, rollback=MagicMock())
        fake_env = MagicMock(cr=fake_cr)
        fake_session = MagicMock(env=fake_env, id=1)

        with (
            patch.object(session_module.modules.module, 'current_test', False),
            patch.object(session_module.time, 'sleep'),
        ):
            session_module.AISession._commit_safe(fake_session)

        self.assertEqual(
            attempts['commit'], session_module.MAX_TRIES_ON_CONCURRENCY_FAILURE,
        )
        self.assertEqual(
            fake_cr.rollback.call_count,
            session_module.MAX_TRIES_ON_CONCURRENCY_FAILURE,
        )
        fake_session.invalidate_recordset.assert_called_once()
