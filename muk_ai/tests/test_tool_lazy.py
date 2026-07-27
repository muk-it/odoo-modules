from __future__ import annotations

import json
from unittest.mock import patch

from odoo.addons.muk_ai.tests.common import AITestCommon, ToolCatalogMixin
from odoo.addons.muk_ai.tools.call import (
    TOOL_SUMMARY_MAX_CHARS,
    format_tool_signature,
    summarize_tool_description,
)


class TestToolLazy(ToolCatalogMixin, AITestCommon):
    """Verify lazy tool-schema loading and on-demand tool execution."""

    # ----------------------------------------------------------
    # Setup
    # ----------------------------------------------------------

    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls.session = cls.env['muk_ai.session'].create({'name': 'Lazy session'})
        cls.catalog = [
            {
                'name': 'list_models',
                'description': 'List installed models',
                'inputSchema': {'type': 'object'},
            },
            {
                'name': 'search_count',
                'description': 'Search records',
                'inputSchema': {'type': 'object'},
            },
            {
                'name': 'read_records',
                'description': 'Read records',
                'inputSchema': {'type': 'object'},
            },
            {
                'name': 'rare_tool',
                'description': 'Rarely used',
                'inputSchema': {
                    'type': 'object',
                    'properties': {'x': {'type': 'string'}},
                },
            },
            {
                'name': 'another_rare',
                'description': 'Also rare',
                'inputSchema': {'type': 'object'},
            },
        ]

    # ----------------------------------------------------------
    # Tests: tool index in system prompt
    # ----------------------------------------------------------

    def test_system_message_includes_tool_index(self):
        with self._patch_catalog():
            system_text = self.session._system_message()['content'][0]['text']
        self.assertIn('<available_tools>', system_text)
        self.assertIn('</available_tools>', system_text)
        for name in ('rare_tool', 'another_rare'):
            self.assertIn(name, system_text)

    def test_effective_system_prompt_excludes_tool_index(self):
        with self._patch_catalog():
            prompt = self.session._effective_system_prompt()
        self.assertNotIn('<available_tools>', prompt)

    def test_a_summary_stops_at_the_first_sentence(self):
        self.assertEqual(
            summarize_tool_description('Export records. Field paths use "/".'),
            'Export records.',
        )

    def test_a_summary_collapses_whitespace_and_newlines(self):
        self.assertEqual(
            summarize_tool_description('Fetch a\n  resource\tby uri'),
            'Fetch a resource by uri',
        )

    def test_a_paragraph_without_an_early_full_stop_is_capped(self):
        summary = summarize_tool_description('x' * 40 + ' ' + 'y' * 300 + '. Tail.')
        self.assertLessEqual(len(summary), TOOL_SUMMARY_MAX_CHARS)
        self.assertTrue(summary.endswith('…'))

    def test_deferred_tools_are_listed_with_signature_and_summary(self):
        with self._patch_catalog():
            block = self.session._build_available_tools_block()
        self.assertIn('rare_tool(x): Rarely used', block)
        self.assertIn('another_rare: Also rare', block)

    def test_a_signature_stars_the_required_arguments(self):
        self.assertEqual(
            format_tool_signature(
                'export_records',
                {
                    'properties': {'model': {}, 'fields': {}, 'limit': {}},
                    'required': ['model', 'fields'],
                },
            ),
            'export_records(model*, fields*, limit)',
        )

    def test_a_tool_without_arguments_keeps_a_bare_name(self):
        self.assertEqual(format_tool_signature('whoami', {'type': 'object'}), 'whoami')
        self.assertEqual(format_tool_signature('whoami', None), 'whoami')

    def test_a_malformed_user_authored_schema_falls_back_to_the_name(self):
        for schema in (
            {'properties': 5},
            {'properties': True},
            {'properties': 'xy'},
            'garbage',
            [],
        ):
            self.assertEqual(format_tool_signature('rare_tool', schema), 'rare_tool')

    def test_a_non_list_required_marks_nothing_as_required(self):
        self.assertEqual(
            format_tool_signature(
                'rare_tool', {'properties': {'model': {}}, 'required': 'model'}
            ),
            'rare_tool(model)',
        )

    def test_a_long_description_is_truncated_on_a_word_boundary(self):
        long_tool = {
            'name': 'rare_tool',
            'description': 'word ' * 200,
            'inputSchema': {'type': 'object'},
        }
        with patch.object(
            type(self.env['muk_mcp.tool']),
            'get_tools',
            autospec=True,
            return_value=[long_tool],
        ):
            block = self.session._build_available_tools_block()
        line = next(li for li in block.splitlines() if li.startswith('rare_tool:'))
        self.assertLess(len(line), TOOL_SUMMARY_MAX_CHARS + 20)
        self.assertTrue(line.endswith('…'))

    def test_a_tool_without_a_description_is_listed_by_name_alone(self):
        with patch.object(
            type(self.env['muk_mcp.tool']),
            'get_tools',
            autospec=True,
            return_value=[{'name': 'rare_tool', 'inputSchema': {'type': 'object'}}],
        ):
            block = self.session._build_available_tools_block()
        self.assertIn('\nrare_tool\n', block)

    def test_available_tools_block_omitted_when_catalog_empty(self):
        with patch.object(
            type(self.env['muk_mcp.tool']),
            'get_tools',
            autospec=True,
            return_value=[],
        ):
            block = self.session._build_available_tools_block()
        self.assertEqual(block, '')

    # ----------------------------------------------------------
    # Tests: schema is small by default
    # ----------------------------------------------------------

    def test_default_schema_only_loads_essentials_and_meta(self):
        with self._patch_catalog():
            schema = self.session._get_tool_schema()
        names = {entry['name'] for entry in schema}
        self.assertIn('list_models', names)
        self.assertIn('search_count', names)
        self.assertIn('read_records', names)
        self.assertIn('tool_load', names)
        self.assertIn('ask_user', names)
        self.assertNotIn('rare_tool', names)
        self.assertNotIn('another_rare', names)

    def test_essentials_silently_dropped_if_not_in_catalog(self):
        smaller = [
            {
                'name': 'list_models',
                'description': '',
                'inputSchema': {'type': 'object'},
            }
        ]
        with patch.object(
            type(self.env['muk_mcp.tool']),
            'get_tools',
            autospec=True,
            return_value=smaller,
        ):
            schema = self.session._get_tool_schema()
        names = {entry['name'] for entry in schema}
        self.assertEqual(names, {'list_models', 'ask_user'})

    def test_ask_user_omitted_when_approval_off(self):
        self.session.override_approval_mode = 'off'
        with self._patch_catalog():
            schema = self.session._get_tool_schema()
        names = {entry['name'] for entry in schema}
        self.assertNotIn('ask_user', names)
        self.assertIn('tool_load', names)

    # ----------------------------------------------------------
    # Tests: tool_load dispatch
    # ----------------------------------------------------------

    def test_tool_load_known_name_loads_and_persists(self):
        with self._patch_catalog():
            result, ok = self.session._dispatch_tool_call(
                'tool_load',
                {'names': ['rare_tool']},
                'call_1',
            )
        self.assertTrue(ok)
        self.assertIn('rare_tool', result['loaded'])
        self.assertEqual(result['loaded']['rare_tool']['description'], 'Rarely used')
        self.assertEqual(result['unknown'], [])
        self.assertIn('rare_tool', list(self.session.expanded_tool_names or []))

    def test_tool_load_unknown_name_returned_in_unknown(self):
        with self._patch_catalog():
            result, ok = self.session._dispatch_tool_call(
                'tool_load',
                {'names': ['no_such_tool']},
                'call_2',
            )
        self.assertFalse(ok)
        self.assertIn('error', result)
        self.assertEqual(result['loaded'], {})
        self.assertEqual(result['unknown'], ['no_such_tool'])
        self.assertNotIn('no_such_tool', list(self.session.expanded_tool_names or []))

    def test_tool_load_partial_resolution_is_not_an_error(self):
        with self._patch_catalog():
            result, ok = self.session._dispatch_tool_call(
                'tool_load',
                {'names': ['rare_tool', 'no_such_tool']},
                'call_partial',
            )
        self.assertTrue(ok)
        self.assertNotIn('error', result)
        self.assertIn('rare_tool', result['loaded'])
        self.assertEqual(result['unknown'], ['no_such_tool'])

    def test_tool_load_strips_namespace_prefix(self):
        with self._patch_catalog():
            result, ok = self.session._dispatch_tool_call(
                'tool_load',
                {'names': ['functions.rare_tool']},
                'call_ns',
            )
        self.assertTrue(ok)
        self.assertNotIn('error', result)
        self.assertIn('rare_tool', result['loaded'])
        self.assertEqual(result['unknown'], [])
        self.assertIn('rare_tool', list(self.session.expanded_tool_names or []))

    def test_tool_load_exact_match_wins_over_prefix_fallback(self):
        dotted = [
            {
                'name': 'server.rare_tool',
                'description': 'Namespaced tool',
                'inputSchema': {'type': 'object'},
            },
            {
                'name': 'rare_tool',
                'description': 'Bare tool',
                'inputSchema': {'type': 'object'},
            },
        ]
        session = self.env['muk_ai.session'].create({'name': 'Dotted catalog'})
        with patch.object(
            type(self.env['muk_mcp.tool']),
            'get_tools',
            autospec=True,
            return_value=dotted,
        ):
            result, _ok = session._dispatch_tool_call(
                'tool_load',
                {'names': ['server.rare_tool']},
                'call_dotted',
            )
        self.assertIn('server.rare_tool', result['loaded'])
        self.assertNotIn('rare_tool', result['loaded'])

    def test_tool_load_namespaced_inline_call_executes(self):
        with (
            self._patch_catalog(),
            patch.object(
                type(self.session),
                '_dispatch_tool_call',
                autospec=True,
                return_value=('called', True),
            ) as dispatch,
        ):
            result = self.session._dispatch_tool_load(
                {
                    'names': ['functions.rare_tool'],
                    'call': {'name': 'functions.rare_tool', 'arguments': {'x': '1'}},
                },
                parent_call_id='call_ns_inline',
            )
        self.assertNotIn('error', result['call'])
        self.assertEqual(result['call']['name'], 'rare_tool')
        self.assertTrue(result['call']['ok'])
        self.assertEqual(dispatch.call_args[0][1], 'rare_tool')

    def test_tool_load_inline_call_accepts_flat_arguments(self):
        with (
            self._patch_catalog(),
            patch.object(
                type(self.session),
                '_dispatch_tool_call',
                autospec=True,
                return_value=('called', True),
            ) as dispatch,
        ):
            result = self.session._dispatch_tool_load(
                {
                    'names': ['rare_tool'],
                    'call': {'name': 'rare_tool', 'x': '1'},
                },
                parent_call_id='call_flat',
            )
        self.assertTrue(result['call']['ok'])
        self.assertEqual(dispatch.call_args[0][2], {'x': '1'})

    def test_tool_load_inline_call_refuses_filtered_tool(self):
        agent = self.env['muk_ai.agent'].create(
            {
                'name': 'Filtered inline call',
                'tool_filter': ['another_rare'],
                'approval_mode': 'off',
            }
        )
        session = self.env['muk_ai.session'].create(
            {
                'name': 'Filtered inline call',
                'agent_id': agent.id,
            }
        )
        with self._patch_catalog():
            result = session._dispatch_tool_load(
                {
                    'names': ['another_rare'],
                    'call': {'name': 'read_records', 'arguments': {}},
                },
                parent_call_id='call_bypass',
            )
        self.assertIn('another_rare', result['loaded'])
        self.assertIn('error', result['call'])
        self.assertNotIn('output', result['call'])

    def test_tool_load_empty_names_errors(self):
        result, _ok = self.session._dispatch_tool_call(
            'tool_load',
            {'names': []},
            'call_3',
        )
        self.assertIn('error', result)

    def test_tool_load_missing_names_errors(self):
        result, _ok = self.session._dispatch_tool_call(
            'tool_load',
            {},
            'call_4',
        )
        self.assertIn('error', result)

    def test_tool_load_dedupes_existing_expanded(self):
        self.session.expanded_tool_names = ['rare_tool']
        with self._patch_catalog():
            self.session._dispatch_tool_call(
                'tool_load',
                {'names': ['rare_tool', 'another_rare']},
                'call_5',
            )
        loaded = list(self.session.expanded_tool_names or [])
        self.assertEqual(loaded.count('rare_tool'), 1)
        self.assertIn('another_rare', loaded)

    def test_loaded_tool_appears_in_subsequent_schema(self):
        with self._patch_catalog():
            self.session._dispatch_tool_call(
                'tool_load',
                {'names': ['rare_tool']},
                'call_6',
            )
            schema = self.session._get_tool_schema()
        names = {entry['name'] for entry in schema}
        self.assertIn('rare_tool', names)

    # ----------------------------------------------------------
    # Tests: agent essentials
    # ----------------------------------------------------------

    def test_agent_custom_essentials_used(self):
        agent = self.env['muk_ai.agent'].create(
            {
                'name': 'Custom essentials',
                'essential_tool_names': ['rare_tool', 'another_rare'],
            }
        )
        session = self.env['muk_ai.session'].create(
            {
                'name': 'Custom session',
                'agent_id': agent.id,
            }
        )
        with self._patch_catalog():
            schema = session._get_tool_schema()
        names = {entry['name'] for entry in schema}
        self.assertIn('rare_tool', names)
        self.assertIn('another_rare', names)
        self.assertIn('tool_load', names)
        self.assertNotIn('list_models', names)

    def test_agent_essentials_intersect_filter(self):
        agent = self.env['muk_ai.agent'].create(
            {
                'name': 'Filtered agent',
                'essential_tool_names': ['list_models', 'rare_tool'],
                'tool_filter': ['list_models'],
            }
        )
        session = self.env['muk_ai.session'].create(
            {
                'name': 'Filtered session',
                'agent_id': agent.id,
            }
        )
        with self._patch_catalog():
            schema = session._get_tool_schema()
        names = {entry['name'] for entry in schema}
        self.assertIn('list_models', names)
        self.assertNotIn('rare_tool', names)

    def test_tool_load_respects_filter(self):
        agent = self.env['muk_ai.agent'].create(
            {
                'name': 'Filtered for load',
                'tool_filter': ['list_models'],
            }
        )
        session = self.env['muk_ai.session'].create(
            {
                'name': 'Filtered for load',
                'agent_id': agent.id,
            }
        )
        with self._patch_catalog():
            result, _ok = session._dispatch_tool_call(
                'tool_load',
                {'names': ['rare_tool']},
                'call_7',
            )
        self.assertEqual(result['loaded'], {})
        self.assertIn('rare_tool', result['unknown'])
        self.assertNotIn('rare_tool', list(session.expanded_tool_names or []))

    # ----------------------------------------------------------
    # Tests: agent helper
    # ----------------------------------------------------------

    def test_agent_get_essential_tool_names_defaults(self):
        agent = self.env['muk_ai.agent'].create({'name': 'Defaults'})
        defaults = agent._get_essential_tool_names()
        for name in ('list_models', 'search_count', 'read_records'):
            self.assertIn(name, defaults)

    def test_agent_get_essential_tool_names_uses_configured_list(self):
        agent = self.env['muk_ai.agent'].create(
            {
                'name': 'Configured',
                'essential_tool_names': ['foo', 'bar', 'baz'],
            }
        )
        self.assertEqual(
            agent._get_essential_tool_names(),
            ['foo', 'bar', 'baz'],
        )

    def test_default_essential_tool_names_is_overridable(self):
        defaults = self.env['muk_ai.agent']._get_default_essential_tool_names()
        for name in ('list_models', 'search_count', 'read_records'):
            self.assertIn(name, defaults)

    # ----------------------------------------------------------
    # Tests: deferred-vs-eager end-to-end parity
    # ----------------------------------------------------------

    def test_deferred_loop_executes_target_tool_like_eager(self):
        agent = self.env['muk_ai.agent'].create(
            {
                'name': 'Parity agent',
                'approval_mode': 'off',
            }
        )
        session_lazy = self.env['muk_ai.session'].create(
            {
                'name': 'Lazy parity',
                'agent_id': agent.id,
            }
        )
        session_eager = self.env['muk_ai.session'].create(
            {
                'name': 'Eager parity',
                'agent_id': agent.id,
            }
        )
        session_eager.expanded_tool_names = ['rare_tool']
        captured_lazy = []
        captured_eager = []

        def make_provider(captured, scenario):
            queue = list(scenario)

            def fake(self_arg, inputs, tools_schema=None, **kwargs):
                captured.append(
                    {
                        'tools': sorted(t['name'] for t in (tools_schema or [])),
                    }
                )
                if not queue:
                    msg = 'exhausted scripted provider responses'
                    raise AssertionError(msg)
                return queue.pop(0)

            return patch.object(
                type(self.provider),
                '_request_responses',
                autospec=True,
                side_effect=fake,
            )

        def tool_call(name, arguments, call_id):
            return {
                'text': '',
                'tool_calls': [
                    {
                        'call_id': call_id,
                        'name': name,
                        'arguments': arguments,
                    }
                ],
                'carry_inputs': [
                    {
                        'type': 'function_call',
                        'name': name,
                        'arguments': json.dumps(arguments),
                        'call_id': call_id,
                    }
                ],
                'usage': {'input_tokens': 4, 'output_tokens': 2},
            }

        def text_payload(text):
            return {
                'text': text,
                'tool_calls': [],
                'carry_inputs': [
                    {
                        'type': 'message',
                        'role': 'assistant',
                        'content': [{'type': 'output_text', 'text': text}],
                    }
                ],
                'usage': {'input_tokens': 3, 'output_tokens': 1},
            }

        def fake_execute(self_arg, name, arguments, env, enforce_scope):
            return f'{{"called": "{name}", "x": "{arguments.get("x", "")}"}}', {}, None

        lazy_scenario = [
            tool_call('tool_load', {'names': ['rare_tool']}, 'c1'),
            tool_call('rare_tool', {'x': 'hello'}, 'c2'),
            text_payload('done'),
        ]
        eager_scenario = [
            tool_call('rare_tool', {'x': 'hello'}, 'c1'),
            text_payload('done'),
        ]

        tool_patch = patch.object(
            type(self.env['muk_mcp.tool']),
            '_execute',
            autospec=True,
            side_effect=fake_execute,
        )

        with (
            self._patch_catalog(),
            tool_patch,
            make_provider(captured_lazy, lazy_scenario),
        ):
            session_lazy.start('list rare')
        with (
            self._patch_catalog(),
            tool_patch,
            make_provider(captured_eager, eager_scenario),
        ):
            session_eager.start('list rare')

        self.assertEqual(session_lazy.state, 'done')
        self.assertEqual(session_eager.state, 'done')
        self.assertEqual(session_lazy.last_text, 'done')
        self.assertEqual(session_eager.last_text, 'done')
        self.assertIn('rare_tool', list(session_lazy.expanded_tool_names or []))

        def tool_results(session):
            return [
                event.payload
                for event in session.event_ids
                if event.kind == 'tool_result'
                and event.payload.get('name') == 'rare_tool'
            ]

        lazy_results = tool_results(session_lazy)
        eager_results = tool_results(session_eager)
        self.assertEqual(len(lazy_results), 1)
        self.assertEqual(len(eager_results), 1)
        self.assertEqual(
            lazy_results[0].get('result'),
            eager_results[0].get('result'),
        )

        first_lazy_round_tools = captured_lazy[0]['tools']
        self.assertIn('tool_load', first_lazy_round_tools)
        self.assertNotIn('rare_tool', first_lazy_round_tools)
        second_lazy_round_tools = captured_lazy[1]['tools']
        self.assertIn('rare_tool', second_lazy_round_tools)
