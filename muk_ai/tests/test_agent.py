from __future__ import annotations

from contextlib import closing

from odoo import Command, fields, models, release
from odoo.exceptions import UserError
from odoo.tests import new_test_user

from odoo.addons.muk_ai.tests.common import AITestCommon, text_payload


class TestAgent(AITestCommon):
    """Verify what an agent puts in front of the model, and how its prompt evolves."""

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    def _agent(self, **values) -> models.BaseModel:
        """Create an agent named after the test."""
        return self.env['muk_ai.agent'].create({'name': 'Test Agent', **values})

    def _request(self, session: models.BaseModel, message: str = 'go') -> dict:
        """Send ``message`` in ``session`` and return the request the model received."""
        with self._mock_responses([text_payload()]) as requests:
            session.send_message(message)
        return requests[0]

    # ----------------------------------------------------------
    # Tests
    # ----------------------------------------------------------

    def test_the_system_prompt_is_rendered_from_its_template(self):
        today = fields.Date.context_today(self.env['muk_ai.agent']).isoformat()
        company = self.env.company.name
        for prompt, values, expected in (
            (
                'Odoo {{ odoo_version }} ({{ odoo_series }}).',
                {},
                f'Odoo {release.version} ({release.series}).',
            ),
            (
                'Approvals {{ approval_mode }}.',
                {'approval_mode': 'off'},
                'Approvals off.',
            ),
            (
                'For {{ company.name }} on {{ today }}.',
                {},
                f'For {company} on {today}.',
            ),
            ('Leak {{ env.cr.__class__ }}.', {}, 'Leak {{ env.cr.__class__ }}.'),
        ):
            with self.subTest(prompt=prompt):
                agent = self._agent(system_prompt=prompt, **values)
                request = self._request(self._session(agent_id=agent.id))
                self.assertTrue(
                    self._system_prompt(request).startswith(f'{expected}\n\n')
                )
                rendered, error = agent._render_prompt_safe(prompt)
                if prompt == expected:
                    self.assertEqual(rendered, prompt)
                    self.assertIn('__class__', error)

    def test_the_runtime_block_states_the_facts_of_the_session(self):
        company = self.env.company
        extra = self.env['res.company'].create({'name': 'Second Test Company'})
        agent = self._agent()
        for companies, line in (
            (company, ''),
            (company | extra, f'Companies accessible: {company.name}, {extra.name}'),
        ):
            with self.subTest(companies=companies.mapped('name')):
                user = new_test_user(
                    self.env,
                    login=f'runtime-{len(companies)}',
                    company_id=company.id,
                    company_ids=[Command.set(companies.ids)],
                    tz='Europe/Vienna',
                )
                session = (
                    self.env['muk_ai.session']
                    .with_user(user)
                    .create({'name': 'Facts', 'agent_id': agent.id})
                )
                system = self._system_prompt(self._request(session))
                for fact in (
                    f'Odoo: {release.version}',
                    f'Date: {fields.Date.context_today(session).isoformat()}',
                    f'User: {user.name} (res.users,{user.id}) - tz Europe/Vienna',
                    f'Company: {company.name} (res.company,{company.id})',
                    'Approval mode: ask',
                ):
                    self.assertIn(fact, system)
                self.assertEqual('Companies accessible' in system, bool(line))
                self.assertIn(line, system)
        self.env['ir.model']._get('res.partner').ai_sensitive = True
        gate = 'Approval gate (the system asks the user): res.partner, res.users'
        self.assertIn(gate, self._system_prompt(self._request(session)))
        session.set_approval_mode('off')
        system = self._system_prompt(self._request(session))
        self.assertIn('Approval mode: off', system)
        self.assertNotIn('Approval gate', system)

    def test_a_new_chat_takes_the_default_agent(self):
        first = self._agent(sequence=0, system_prompt='First prompt.')
        picked = self._agent(system_prompt='Picked prompt.')
        everyone = self.env['muk_ai.agent'].search([])
        pick = (self.env.company, {'default_ai_agent_id': picked.id})
        for writes, values, expected, prompt in (
            ((pick,), {}, picked, 'Picked prompt.'),
            ((pick,), {'agent_id': False}, everyone.browse(), 'Picked prompt.'),
            ((pick, (picked, {'active': False})), {}, first, 'First prompt.'),
            (
                ((self.env.company, {'default_ai_agent_id': False}),),
                {},
                first,
                'First prompt.',
            ),
            (((everyone, {'active': False}),), {}, everyone.browse(), None),
        ):
            with (
                self.subTest(values=values, writes=len(writes)),
                closing(self.env.cr.savepoint()),
            ):
                for record, vals in writes:
                    record.write(vals)
                session = self._session(**values)
                self.assertEqual(session.agent_id, expected)
                request = self._request(session)
                system = self._system_prompt(request)
                used = [
                    text
                    for text in ('Picked prompt.', 'First prompt.')
                    if text in system
                ]
                self.assertEqual(used, [prompt] if prompt else [])

    def test_the_effort_offered_follows_the_model_the_agent_runs_on(self):
        capable = self._create_model('gpt-effort', reasoning_efforts=['low', 'high'])
        plain = self._create_model('gpt-no-effort')
        self.provider.default_chat_model_id = capable
        agent = self._agent(model_id=capable.id, reasoning_effort='high')
        for values, options, effort in (
            ({}, ['low', 'high'], 'high'),
            ({'model_id': plain.id}, [], False),
            ({'model_id': False, 'reasoning_effort': 'low'}, ['low', 'high'], 'low'),
        ):
            with self.subTest(values=values):
                agent.write(values)
                session = self._session(agent_id=agent.id)
                request = self._request(session)
                self.assertEqual(agent.reasoning_effort_options or [], options)
                self.assertEqual(agent.reasoning_effort, effort)
                self.assertEqual(
                    session.get_snapshot()['reasoning_effort_options'], options
                )
                self.assertEqual(request['reasoning_effort'], effort or None)

    def test_the_tool_filter_decides_which_tools_the_model_can_reach(self):
        narrow = self._agent(
            tool_filter=['search_read', 'read_records', 'describe_model'],
            essential_tool_names=['search_read'],
        )
        for agent, expanded, offered, deferred in (
            (
                narrow,
                [],
                {'search_read', 'tool_load', 'ask_user'},
                {'read_records', 'describe_model'},
            ),
            (
                narrow,
                ['read_records', 'create_records'],
                {'search_read', 'read_records', 'tool_load', 'ask_user'},
                {'describe_model'},
            ),
            (self._agent(), [], None, {'create_records'}),
        ):
            with self.subTest(filtered=bool(agent.tool_filter), expanded=expanded):
                session = self._session(agent_id=agent.id)
                session.expanded_tool_names = expanded
                request = self._request(session)
                tools = self._tools(request)
                listed = self._system_prompt(request).partition('<available_tools>')[2]
                if offered:
                    self.assertEqual(tools, offered)
                else:
                    self.assertLessEqual({'search_read', 'read_records'}, tools)
                for name in deferred:
                    self.assertNotIn(name, tools)
                    self.assertIn(f'\n{name}(', listed)
                self.assertEqual('create_records(' in listed, not agent.tool_filter)

    def test_the_agent_lists_its_suggestions_and_counts_its_chats(self):
        agent = self._agent(
            suggestion_ids=[
                Command.create({'label': 'Later', 'prompt': 'p-b', 'sequence': 20}),
                Command.create({'label': 'First', 'prompt': 'p-a', 'sequence': 10}),
            ]
        )
        self._session(agent_id=agent.id)
        self._session(agent_id=agent.id)
        agent.invalidate_recordset()
        self.assertEqual(
            agent.suggestions,
            [{'label': 'First', 'prompt': 'p-a'}, {'label': 'Later', 'prompt': 'p-b'}],
        )
        self.assertEqual(agent.session_count, 2)

    def test_a_prompt_change_is_kept_as_a_revision(self):
        forged = {'prompt_history': {'system_prompt': [{'body': 'forged'}]}}
        for initial, writes, bodies in (
            ('v1', [{'system_prompt': 'v2'}], ['v1']),
            ('v1', [{'system_prompt': 'v1'}], []),
            (False, [{'system_prompt': 'first'}], []),
            ('v1', [{'name': 'Renamed'}, forged], []),
            (
                'v0',
                [{'system_prompt': f'v{index}'} for index in range(1, 6)],
                ['v4', 'v3', 'v2', 'v1', 'v0'],
            ),
        ):
            with self.subTest(initial=initial, writes=writes):
                agent = self._agent(system_prompt=initial)
                for vals in writes:
                    agent.write(vals)
                self.assertEqual(agent.prompt_history_count, len(bodies))
                self.assertEqual(
                    [
                        agent.prompt_history_get_content('system_prompt', index)
                        for index in range(len(bodies))
                    ],
                    bodies,
                )

    def test_a_revision_can_be_compared_and_restored(self):
        agent = self._agent(system_prompt='line one\nline two')
        agent.write({'system_prompt': 'line one\nline three'})
        entry = agent.prompt_history_metadata['system_prompt'][0]
        self.assertNotIn('body', entry)
        self.assertEqual(entry['create_uid'], self.env.uid)
        diff = agent.prompt_history_unified_diff('system_prompt', 0)
        self.assertIn('-line two', diff)
        self.assertIn('+line three', diff)
        self.assertNotIn('-line one', diff)
        action = agent.prompt_history_restore('system_prompt', 0)
        self.assertEqual(
            (action['params']['type'], action['params']['next']['tag']),
            ('success', 'soft_reload'),
        )
        self.assertEqual(agent.system_prompt, 'line one\nline two')
        self.assertEqual(
            agent.prompt_history_get_content('system_prompt', 0),
            'line one\nline three',
        )
        with self.assertRaisesRegex(UserError, 'Revision not found'):
            agent.prompt_history_get_content('system_prompt', 2)
