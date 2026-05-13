from odoo.exceptions import UserError
from odoo.tests.common import tagged

from .common import BridgeTestCommon


@tagged('post_install', '-at_install')
class TestEeToolsViaMcp(BridgeTestCommon):

    # ----------------------------------------------------------
    # Setup
    # ----------------------------------------------------------

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.action = cls.env['ir.actions.server'].create({
            'name': 'Bridge Test Echo Action',
            'model_id': cls.env['ir.model']._get_id('res.users'),
            'state': 'code',
            'code': "ai['result'] = 'echoed: ' + (msg or '')",
            'use_in_ai': True,
            'ai_tool_description': 'Echo a message back',
            'ai_tool_schema': (
                '{"type": "object", '
                '"properties": {"msg": {"type": "string"}}, '
                '"required": ["msg"]}'
            ),
        })
        cls.topic = cls.env['ai.topic'].create({
            'name': 'Bridge Echo Topic',
            'tool_ids': [(6, 0, [cls.action.id])],
        })
        cls.agent = cls.env['muk_ai.agent'].create({
            'name': 'Bridge Echo Agent',
            'ee_topic_ids': [(6, 0, [cls.topic.id])],
        })

    # ----------------------------------------------------------
    # Helpers
    # ----------------------------------------------------------

    def _ee_tool_name(self):
        xml_ids = self.action.get_external_id()
        if xml_id := xml_ids.get(self.action.id):
            return f"ee_action_{xml_id.split('.')[1]}"
        return f"ee_action_action_{self.action.id}"

    def _make_session(self, **vals):
        defaults = {'name': 'EE Tool Session', 'agent_id': self.agent.id}
        defaults.update(vals)
        return self.env['muk_ai.session'].create(defaults)

    # ----------------------------------------------------------
    # Tests
    # ----------------------------------------------------------

    def test_ee_tools_listed_in_session_catalog(self):
        session = self._make_session()
        session = session.with_context(muk_ai_session_agent_id=self.agent.id)
        names = {t['name'] for t in session._get_filtered_catalog()}
        self.assertIn(self._ee_tool_name(), names)

    def test_ee_tools_absent_without_topics(self):
        agent = self.env['muk_ai.agent'].create({'name': 'No EE'})
        session = self.env['muk_ai.session'].create({
            'name': 'Plain Session',
            'agent_id': agent.id,
        })
        session = session.with_context(muk_ai_session_agent_id=agent.id)
        names = {t['name'] for t in session._get_filtered_catalog()}
        self.assertNotIn(self._ee_tool_name(), names)

    def test_ee_tools_absent_when_no_context_marker(self):
        Tool = self.env['muk_mcp.tool']
        tools = Tool.get_tools(registry='odoo')
        names = {t['name'] for t in tools}
        self.assertNotIn(self._ee_tool_name(), names)

    def test_dispatch_runs_action_and_logs(self):
        session = self._make_session()
        tool_name = self._ee_tool_name()
        log_count_before = self.env['muk_mcp.log'].search_count([
            ('session_id', '=', session.id),
        ])
        with self._patch_provider([
            self._tool_payload(tool_name, {'msg': 'hello'}, 'call_a'),
            self._text_payload('done'),
        ]):
            snapshot = session.start('please echo')
        self.assertEqual(snapshot['state'], 'done')
        log_rows = self.env['muk_mcp.log'].search([
            ('session_id', '=', session.id),
            ('tool_name', '=', tool_name),
        ])
        self.assertTrue(log_rows, "ee_action_* call should be logged")
        self.assertGreater(
            self.env['muk_mcp.log'].search_count([
                ('session_id', '=', session.id),
            ]),
            log_count_before,
        )
        self.assertEqual(log_rows[0].user_id, self.env.user)

    def test_read_only_agent_blocks_ee_action(self):
        ro_agent = self.env['muk_ai.agent'].create({
            'name': 'RO Agent',
            'read_only': True,
            'ee_topic_ids': [(6, 0, [self.topic.id])],
        })
        session = self.env['muk_ai.session'].create({
            'name': 'RO Session',
            'agent_id': ro_agent.id,
        })
        session = session.with_context(muk_ai_session_agent_id=ro_agent.id)
        names = {t['name'] for t in session._get_filtered_catalog()}
        self.assertNotIn(
            self._ee_tool_name(), names,
            "ee_action_* must be filtered out for read-only agents.",
        )
        Tool = self.env['muk_mcp.tool']
        with self.assertRaises(UserError):
            Tool._call(
                self._ee_tool_name(),
                {'msg': 'hi'},
                self.env,
                enforce_scope='read',
            )

    def test_name_collision_does_not_clobber(self):
        muk_tools = self.env['muk_mcp.tool'].get_tools(registry='odoo')
        muk_names = {t['name'] for t in muk_tools}
        self.assertFalse(
            any(n.startswith('ee_action_') for n in muk_names),
            "muk_mcp baseline should not ship any ee_action_* names.",
        )
        session = self._make_session()
        session = session.with_context(muk_ai_session_agent_id=self.agent.id)
        names = [t['name'] for t in session._get_tool_schema()]
        self.assertEqual(
            len(names), len(set(names)),
            "Tool names must be unique after merging EE tools.",
        )

    def test_unknown_ee_action_raises(self):
        Tool = self.env['muk_mcp.tool']
        with self.assertRaises(UserError):
            Tool._call('ee_action_does_not_exist', {}, self.env)
