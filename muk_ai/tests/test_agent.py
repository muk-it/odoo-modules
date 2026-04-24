from unittest.mock import patch

from odoo.addons.muk_ai.tools.limits import DEFAULT_CONTEXT_WINDOW

from .common import AITestCommon


class TestAiAgent(AITestCommon):

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    def _make_model(self, model_name, context_window=128000, provider=None):
        return self.env['muk_ai.model'].create({
            'name': model_name,
            'provider_id': (provider or self.provider).id,
            'technical_name': model_name,
            'context_window': context_window,
            'input_rate': 1.0,
            'output_rate': 2.0,
        })

    # ----------------------------------------------------------
    # Tests
    # ----------------------------------------------------------

    def test_apply_tool_filter_empty_allows_all(self):
        agent = self.env['muk_ai.agent'].create({
            'name': 'All tools',
            'tool_filter': [],
        })
        tools = [{'name': 'a'}, {'name': 'b'}]
        self.assertEqual(agent.apply_tool_filter(tools), tools)

    def test_apply_tool_filter_limits_to_allowlist(self):
        agent = self.env['muk_ai.agent'].create({
            'name': 'Read only',
            'tool_filter': ['search_records', 'ask_user'],
        })
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
            [('active', '=', True)], limit=1,
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
        agent = self.env['muk_ai.agent'].create({
            'name': 'Coach',
            'system_prompt': 'You are a helpful coach.',
        })
        session = self.env['muk_ai.session'].create({
            'name': 'With agent',
            'agent_id': agent.id,
        })
        self.assertEqual(session._effective_system_prompt(), 'You are a helpful coach.')

    def test_session_uses_company_default_agent_prompt(self):
        Agent = self.env['muk_ai.agent']
        default_agent = Agent.create({
            'name': 'Company Default',
            'system_prompt': 'Company default prompt.',
        })
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

    def test_provider_capability_flags_default_false(self):
        agent = self.env['muk_ai.agent'].create({'name': 'Plain'})
        self.assertFalse(agent.enable_web_search)
        self.assertFalse(agent.enable_image_generation)
        self.assertFalse(agent.enable_code_interpreter)

    def test_agent_resolve_model_uses_override(self):
        model = self._make_model('test-custom', context_window=128000)
        agent = self.env['muk_ai.agent'].create({
            'name': 'Custom',
            'model_id': model.id,
        })
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
        agent = self.env['muk_ai.agent'].create({
            'name': 'Narrow',
            'tool_filter': ['only_this'],
        })
        session = self.env['muk_ai.session'].create({
            'name': 'Narrow session',
            'agent_id': agent.id,
        })
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
        self.assertEqual([t['name'] for t in schema], ['only_this'])

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

    def test_action_open_prompt_revisions_filters_by_agent(self):
        agent = self.env['muk_ai.agent'].create({'name': 'Historian'})
        action = agent.action_open_prompt_revisions()
        self.assertEqual(action['res_model'], 'muk_ai.agent.revision')
        self.assertIn(('agent_id', '=', agent.id), action['domain'])

    # ----------------------------------------------------------
    # Compute + onchange
    # ----------------------------------------------------------

    def test_compute_tool_filter_options_includes_ask_user(self):
        agent = self.env['muk_ai.agent'].create({'name': 'Options'})
        names = {o['name'] for o in agent.tool_filter_options or []}
        self.assertIn('ask_user', names)

    def test_compute_session_count_matches_created_sessions(self):
        agent = self.env['muk_ai.agent'].create({'name': 'Counter'})
        self.env['muk_ai.session'].create({'name': 's1', 'agent_id': agent.id})
        self.env['muk_ai.session'].create({'name': 's2', 'agent_id': agent.id})
        agent.invalidate_recordset()
        self.assertEqual(agent.session_count, 2)

    def test_compute_revision_count_matches_created_revisions(self):
        agent = self.env['muk_ai.agent'].create({
            'name': 'Historied', 'system_prompt': 'v1',
        })
        self.env['muk_ai.agent.revision'].create({
            'agent_id': agent.id, 'body': 'v1',
        })
        self.env['muk_ai.agent.revision'].create({
            'agent_id': agent.id, 'body': 'v2',
        })
        agent.invalidate_recordset()
        self.assertEqual(agent.revision_count, 2)

    def test_compute_provider_capabilities_mirrors_provider(self):
        model = self._make_model('cap-m', provider=self.provider)
        agent = self.env['muk_ai.agent'].create({
            'name': 'Mirror', 'model_id': model.id,
        })
        self.assertEqual(agent.supports_web_search, self.provider.supports_web_search)
        self.assertEqual(
            agent.supports_image_generation,
            self.provider.supports_image_generation,
        )
        self.assertEqual(
            agent.supports_code_interpreter,
            self.provider.supports_code_interpreter,
        )

    def test_compute_suggestions_reflects_suggestion_records(self):
        agent = self.env['muk_ai.agent'].create({
            'name': 'Suggester',
            'suggestion_ids': [
                (0, 0, {'label': 'A', 'prompt': 'p-a', 'sequence': 10}),
                (0, 0, {'label': 'B', 'prompt': 'p-b', 'sequence': 20}),
            ],
        })
        labels = [s['label'] for s in agent.suggestions or []]
        self.assertEqual(labels, ['A', 'B'])

    def test_get_placeholder_filename_returns_icon_for_image_field(self):
        agent = self.env['muk_ai.agent'].create({'name': 'Img'})
        self.assertEqual(
            agent._get_placeholder_filename('image_1920'),
            'muk_ai/static/description/icon.png',
        )

    def test_get_placeholder_filename_delegates_for_other_fields(self):
        agent = self.env['muk_ai.agent'].create({'name': 'Img2'})
        result = agent._get_placeholder_filename('some_other_field')
        self.assertNotEqual(result, 'muk_ai/static/description/icon.png')
