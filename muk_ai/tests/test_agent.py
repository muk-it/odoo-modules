from __future__ import annotations

from unittest.mock import patch

from odoo import models, release

from odoo.addons.muk_ai.tests.common import AITestCommon
from odoo.addons.muk_ai.tools import DEFAULT_CONTEXT_WINDOW


class TestAiAgent(AITestCommon):
    """Verify AI agent configuration, defaults, tool filtering, and capabilities."""

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    def _make_model(
        self,
        model_name: str,
        context_window: int = 128000,
        provider: models.BaseModel | None = None,
    ) -> models.BaseModel:
        """Create a catalog model record with the given context window.

        :param provider: Provider to attach the model to; defaults to
            ``self.provider``.
        """
        return self.env['muk_ai.model'].create(
            {
                'name': model_name,
                'provider_id': (provider or self.provider).id,
                'technical_name': model_name,
                'context_window': context_window,
                'input_rate': 1.0,
                'output_rate': 2.0,
            }
        )

    # ----------------------------------------------------------
    # Tests
    # ----------------------------------------------------------

    def test_agent_reasoning_effort_follows_model_support(self):
        capable = self._create_model(
            'gpt-5-agent-effort-test', reasoning_efforts=['low', 'high']
        )
        plain = self._create_model('gpt-agent-plain-test')
        agent = self.env['muk_ai.agent'].create(
            {
                'name': 'Effort Agent',
                'model_id': capable.id,
                'reasoning_effort': 'high',
            }
        )
        self.assertEqual(agent.reasoning_effort_options, ['low', 'high'])
        self.assertEqual(agent.reasoning_effort, 'high')
        agent.model_id = plain.id
        self.assertFalse(agent.reasoning_effort_options)
        self.assertFalse(agent.reasoning_effort)

    def test_apply_tool_filter_empty_allows_all(self):
        agent = self.env['muk_ai.agent'].create(
            {
                'name': 'All tools',
                'tool_filter': [],
            }
        )
        tools = [{'name': 'a'}, {'name': 'b'}]
        self.assertEqual(agent.apply_tool_filter(tools), tools)

    def test_apply_tool_filter_limits_to_allowlist(self):
        agent = self.env['muk_ai.agent'].create(
            {
                'name': 'Read only',
                'tool_filter': ['search_records', 'ask_user'],
            }
        )
        tools = [
            {'name': 'search_records'},
            {'name': 'execute_method'},
            {'name': 'ask_user'},
        ]
        filtered = agent.apply_tool_filter(tools)
        self.assertEqual({t['name'] for t in filtered}, {'search_records', 'ask_user'})

    def test_default_from_company(self):
        agent = self.env['muk_ai.agent'].create({'name': 'CompanyPick'})
        self.env.company.default_ai_agent_id = agent
        self.assertEqual(self.env['muk_ai.agent']._get_default(), agent)

    def test_default_falls_back_to_any_active_agent(self):
        self.env.company.default_ai_agent_id = False
        active = self.env['muk_ai.agent'].search(
            [('active', '=', True)],
            limit=1,
        )
        self.assertTrue(active)
        self.assertEqual(self.env['muk_ai.agent']._get_default(), active)

    def test_default_skips_archived_company_pick(self):
        agent = self.env['muk_ai.agent'].create({'name': 'Retired'})
        self.env.company.default_ai_agent_id = agent
        agent.active = False
        result = self.env['muk_ai.agent']._get_default()
        self.assertNotEqual(result, agent)
        self.assertTrue(result)

    def test_session_uses_default_agent(self):
        default = self.env['muk_ai.agent'].create({'name': 'Autopick'})
        self.env.company.default_ai_agent_id = default
        session = self.env['muk_ai.session'].create({'name': 'Fresh'})
        self.assertEqual(session.agent_id, default)

    def test_session_uses_agent_system_prompt(self):
        agent = self.env['muk_ai.agent'].create(
            {
                'name': 'Coach',
                'system_prompt': 'You are a helpful coach.',
            }
        )
        session = self.env['muk_ai.session'].create(
            {
                'name': 'With agent',
                'agent_id': agent.id,
            }
        )
        self.assertEqual(session._effective_system_prompt(), 'You are a helpful coach.')

    def test_session_uses_company_default_agent_prompt(self):
        Agent = self.env['muk_ai.agent']
        default_agent = Agent.create(
            {
                'name': 'Company Default',
                'system_prompt': 'Company default prompt.',
            }
        )
        self.env.company.default_ai_agent_id = default_agent
        session = self.env['muk_ai.session'].create({'name': 'No agent'})
        self.assertEqual(
            session._effective_system_prompt(),
            'Company default prompt.',
        )

    def test_session_empty_prompt_when_no_agent(self):
        Agent = self.env['muk_ai.agent']
        self.env.company.default_ai_agent_id = False
        Agent.search([]).write({'active': False})
        session = self.env['muk_ai.session'].create({'name': 'No agent'})
        self.assertEqual(session._effective_system_prompt(), '')

    def test_render_eval_context_exposes_odoo_version(self):
        ctx = self.env['muk_ai.agent']._get_default()._prompt_eval_context()
        self.assertEqual(ctx['odoo_version'], release.version)
        self.assertEqual(ctx['odoo_series'], release.series)

    def test_system_prompt_renders_odoo_version_template(self):
        agent = self.env['muk_ai.agent'].create(
            {
                'name': 'Versioned',
                'system_prompt': 'You are an Odoo {{ odoo_version }} assistant.',
            }
        )
        session = self.env['muk_ai.session'].create(
            {
                'name': 'Versioned session',
                'agent_id': agent.id,
            }
        )
        rendered = session._effective_system_prompt()
        self.assertIn(release.version, rendered)
        self.assertNotIn('{{', rendered)

    def test_runtime_block_contains_core_facts(self):
        session = self.env['muk_ai.session'].create({'name': 'Runtime'})
        block = session._build_runtime_block()
        self.assertIn('<runtime>', block)
        self.assertIn('</runtime>', block)
        self.assertIn(f'Odoo: {release.version}', block)
        self.assertIn('Date: ', block)
        self.assertIn(f'(res.users,{self.env.user.id})', block)
        self.assertIn(f'(res.company,{self.env.company.id})', block)
        self.assertIn('Approval mode:', block)

    def test_runtime_block_omits_multi_company_line_when_single(self):
        session = self.env['muk_ai.session'].create({'name': 'SingleCo'})
        single = self.env.user.copy(
            {
                'login': 'single-co-user@example.test',
                'company_ids': [(6, 0, [self.env.company.id])],
                'company_id': self.env.company.id,
            }
        )
        block = session.with_user(single)._build_runtime_block()
        self.assertNotIn('Companies accessible', block)

    def test_runtime_block_emits_multi_company_line_when_multi(self):
        Company = self.env['res.company']
        extra = Company.create({'name': 'MuK Extra Test Co'})
        multi = self.env.user.copy(
            {
                'login': 'multi-co-user@example.test',
                'company_ids': [(6, 0, [self.env.company.id, extra.id])],
                'company_id': self.env.company.id,
            }
        )
        session = self.env['muk_ai.session'].create({'name': 'MultiCo'})
        block = session.with_user(multi)._build_runtime_block()
        self.assertIn('Companies accessible', block)
        self.assertIn('MuK Extra Test Co', block)

    def test_system_message_includes_runtime_block(self):
        agent = self.env['muk_ai.agent'].create(
            {
                'name': 'Inputs',
                'system_prompt': 'Be concise.',
            }
        )
        session = self.env['muk_ai.session'].create(
            {
                'name': 'Inputs session',
                'agent_id': agent.id,
            }
        )
        system_text = session._system_message()['content'][0]['text']
        self.assertIn('Be concise.', system_text)
        self.assertIn('<runtime>', system_text)
        self.assertIn(f'Odoo: {release.version}', system_text)

    def test_effective_system_prompt_excludes_runtime_block(self):
        agent = self.env['muk_ai.agent'].create(
            {
                'name': 'NoRuntime',
                'system_prompt': 'Just the rules.',
            }
        )
        session = self.env['muk_ai.session'].create(
            {
                'name': 'NoRuntime session',
                'agent_id': agent.id,
            }
        )
        prompt = session._effective_system_prompt()
        self.assertNotIn('<runtime>', prompt)

    def test_agent_resolve_model_uses_override(self):
        model = self._make_model('test-custom', context_window=128000)
        agent = self.env['muk_ai.agent'].create(
            {
                'name': 'Custom',
                'model_id': model.id,
            }
        )
        self.assertEqual(agent._resolve_model(), model)
        self.assertEqual(agent._resolve_context_window(), 128000)

    def test_agent_resolve_context_window_falls_back_to_default(self):
        default_model = self._make_model('auto-default', context_window=64000)
        self.provider.default_model_id = default_model
        self.env.company.default_ai_provider_id = self.provider
        agent = self.env['muk_ai.agent'].create({'name': 'Auto'})
        self.assertEqual(agent._resolve_context_window(), 64000)

    def test_agent_resolve_context_window_hard_fallback(self):
        default_provider = self.env['muk_ai.provider']._get_default()
        default_provider.default_model_id = False
        agent = self.env['muk_ai.agent'].create({'name': 'NoModel'})
        self.assertEqual(agent._resolve_context_window(), DEFAULT_CONTEXT_WINDOW)

    def test_session_tool_schema_respects_agent_filter(self):
        agent = self.env['muk_ai.agent'].create(
            {
                'name': 'Narrow',
                'tool_filter': ['only_this'],
                'essential_tool_names': ['only_this'],
            }
        )
        session = self.env['muk_ai.session'].create(
            {
                'name': 'Narrow session',
                'agent_id': agent.id,
            }
        )
        fake = [
            {'name': 'only_this', 'description': '', 'inputSchema': {}},
            {'name': 'banned', 'description': '', 'inputSchema': {}},
        ]
        with patch.object(
            type(self.env['muk_mcp.tool']),
            'get_tools',
            autospec=True,
            return_value=fake,
        ):
            schema = session._get_tool_schema()
        names = [t['name'] for t in schema]
        self.assertIn('only_this', names)
        self.assertNotIn('banned', names)
        session.expanded_tool_names = ['banned']
        with patch.object(
            type(self.env['muk_mcp.tool']),
            'get_tools',
            autospec=True,
            return_value=fake,
        ):
            schema = session._get_tool_schema()
        self.assertNotIn('banned', [t['name'] for t in schema])

    # ----------------------------------------------------------
    # Actions
    # ----------------------------------------------------------

    def test_action_open_sessions_filters_by_agent(self):
        agent = self.env['muk_ai.agent'].create({'name': 'Opener'})
        action = agent.action_open_sessions()
        self.assertEqual(action['type'], 'ir.actions.act_window')
        self.assertEqual(action['res_model'], 'muk_ai.session')
        self.assertIn(('agent_id', '=', agent.id), action['domain'])
        self.assertEqual(action['context']['default_agent_id'], agent.id)

    def test_action_open_prompt_history_targets_system_prompt(self):
        agent = self.env['muk_ai.agent'].create({'name': 'Historian'})
        action = agent.action_open_prompt_history()
        self.assertEqual(action['tag'], 'muk_ai.prompt_history_dialog')
        self.assertEqual(action['params']['res_model'], 'muk_ai.agent')
        self.assertEqual(action['params']['res_id'], agent.id)
        self.assertEqual(action['params']['field_name'], 'system_prompt')

    # ----------------------------------------------------------
    # Compute + onchange
    # ----------------------------------------------------------

    def test_compute_tool_filter_options_lists_the_catalog_sorted_by_name(self):
        agent = self.env['muk_ai.agent'].create({'name': 'Options'})
        options = agent.tool_filter_options or []
        names = [option['name'] for option in options]
        self.assertTrue(names)
        self.assertEqual(names, sorted(names))
        by_name = {option['name']: option for option in options}
        self.assertIn('ask_user', by_name)
        self.assertEqual(set(by_name['ask_user']), {'name', 'category', 'description'})
        self.assertEqual(by_name['ask_user']['category'], 'read')
        self.assertTrue(by_name['ask_user']['description'])

    def test_compute_session_count_matches_created_sessions(self):
        agent = self.env['muk_ai.agent'].create({'name': 'Counter'})
        self.env['muk_ai.session'].create({'name': 's1', 'agent_id': agent.id})
        self.env['muk_ai.session'].create({'name': 's2', 'agent_id': agent.id})
        agent.invalidate_recordset()
        self.assertEqual(agent.session_count, 2)

    def test_prompt_history_count_grows_when_system_prompt_changes(self):
        agent = self.env['muk_ai.agent'].create(
            {
                'name': 'Historied',
                'system_prompt': 'v1',
            }
        )
        agent.write({'system_prompt': 'v2'})
        agent.write({'system_prompt': 'v3'})
        agent.invalidate_recordset()
        self.assertEqual(agent.prompt_history_count, 2)

    def test_provider_capabilities_force_off_the_unsupported_enable_flags(self):
        openai_model = self._make_model('cap-openai', provider=self.provider)
        anthropic_model = self._make_model(
            'cap-anthropic',
            provider=self.provider_anthropic,
        )
        agent = self.env['muk_ai.agent'].create(
            {
                'name': 'Mirror',
                'model_id': openai_model.id,
                'enable_web_search': True,
                'enable_image_generation': True,
                'enable_code_interpreter': True,
            }
        )
        self.assertTrue(agent.supports_web_search)
        self.assertTrue(agent.supports_image_generation)
        self.assertTrue(agent.supports_code_interpreter)
        self.assertTrue(agent.enable_image_generation)
        agent.model_id = anthropic_model.id
        self.assertTrue(agent.supports_web_search)
        self.assertFalse(agent.supports_image_generation)
        self.assertTrue(agent.supports_code_interpreter)
        self.assertFalse(agent.enable_image_generation)
        self.assertTrue(agent.enable_web_search)
        self.assertTrue(agent.enable_code_interpreter)

    def test_compute_suggestions_reflects_suggestion_records(self):
        agent = self.env['muk_ai.agent'].create(
            {
                'name': 'Suggester',
                'suggestion_ids': [
                    (0, 0, {'label': 'A', 'prompt': 'p-a', 'sequence': 10}),
                    (0, 0, {'label': 'B', 'prompt': 'p-b', 'sequence': 20}),
                ],
            }
        )
        labels = [s['label'] for s in agent.suggestions or []]
        self.assertEqual(labels, ['A', 'B'])

    def test_get_placeholder_filename_returns_icon_for_image_fields_only(self):
        agent = self.env['muk_ai.agent'].create({'name': 'Img'})
        image_fields = (
            'image_1920',
            'image_1024',
            'image_512',
            'image_256',
            'image_128',
        )
        for field in image_fields:
            self.assertEqual(
                agent._get_placeholder_filename(field),
                'muk_ai/static/description/icon.png',
            )
        self.assertIs(agent._get_placeholder_filename('some_other_field'), False)
