from __future__ import annotations

import json

from odoo.exceptions import UserError
from odoo.tests.common import tagged

from .common import BridgeTestCommon


@tagged('post_install', '-at_install')
class TestTools(BridgeTestCommon):
    """Test EE action tool exposure, dispatch and access control."""

    # ----------------------------------------------------------
    # Setup
    # ----------------------------------------------------------

    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls.action = cls.env['ir.actions.server'].create(
            {
                'name': 'Bridge Test Echo Action',
                'model_id': cls.env['ir.model']._get_id('res.partner'),
                'state': 'code',
                'code': "ai['result'] = 'echoed: ' + (msg or '')",
                'use_in_ai': True,
                'ai_tool_description': 'Echo a message back',
                'ai_tool_schema': (
                    '{"type": "object", '
                    '"properties": {"msg": {"type": "string"}}, '
                    '"required": ["msg"]}'
                ),
            }
        )
        cls.topic = cls.env['ai.topic'].create(
            {
                'name': 'Bridge Echo Topic',
                'tool_ids': [(6, 0, [cls.action.id])],
            }
        )
        cls.agent = cls.env['muk_ai.agent'].create(
            {
                'name': 'Bridge Echo Agent',
                'ee_topic_ids': [(6, 0, [cls.topic.id])],
            }
        )

    # ----------------------------------------------------------
    # Helpers
    # ----------------------------------------------------------

    def _ee_tool_name(self, action=None) -> str:
        """Return the ``ee_action_*`` tool name for a server action.

        :param action: the action to name; defaults to the fixture action
        """
        action = action or self.action
        xml_ids = action.get_external_id()
        if xml_id := xml_ids.get(action.id):
            return f'ee_action_{xml_id.split(".")[1]}'
        return f'ee_action_action_{action.id}'

    def _make_session(self, **vals):
        """Create a session bound to the fixture agent."""
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
        session = self.env['muk_ai.session'].create(
            {
                'name': 'Plain Session',
                'agent_id': agent.id,
            }
        )
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
        log_count_before = self.env['muk_mcp.log'].search_count(
            [
                ('session_id', '=', session.id),
            ]
        )
        with self._patch_provider(
            [
                self._tool_payload(tool_name, {'msg': 'hello'}, 'call_a'),
                self._text_payload('done'),
            ]
        ):
            snapshot = session.start('please echo')
        self.assertEqual(snapshot['state'], 'done')
        log_rows = self.env['muk_mcp.log'].search(
            [
                ('session_id', '=', session.id),
                ('tool_name', '=', tool_name),
            ]
        )
        self.assertTrue(log_rows, 'ee_action_* call should be logged')
        self.assertGreater(
            self.env['muk_mcp.log'].search_count(
                [
                    ('session_id', '=', session.id),
                ]
            ),
            log_count_before,
        )
        self.assertEqual(log_rows[0].user_id, self.env.user)

    def test_read_only_agent_blocks_ee_action(self):
        ro_agent = self.env['muk_ai.agent'].create(
            {
                'name': 'RO Agent',
                'read_only': True,
                'ee_topic_ids': [(6, 0, [self.topic.id])],
            }
        )
        session = self.env['muk_ai.session'].create(
            {
                'name': 'RO Session',
                'agent_id': ro_agent.id,
            }
        )
        session = session.with_context(muk_ai_session_agent_id=ro_agent.id)
        names = {t['name'] for t in session._get_filtered_catalog()}
        self.assertNotIn(
            self._ee_tool_name(),
            names,
            'ee_action_* must be filtered out for read-only agents.',
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
            'muk_mcp baseline should not ship any ee_action_* names.',
        )
        session = self._make_session()
        session = session.with_context(muk_ai_session_agent_id=self.agent.id)
        names = [t['name'] for t in session._get_tool_schema()]
        self.assertEqual(
            len(names),
            len(set(names)),
            'Tool names must be unique after merging EE tools.',
        )

    def test_unknown_ee_action_raises(self):
        Tool = self.env['muk_mcp.tool']
        with self.assertRaises(UserError):
            Tool._call('ee_action_does_not_exist', {}, self.env)

    def test_out_of_topic_ee_action_rejected(self):
        other_action = self.env['ir.actions.server'].create(
            {
                'name': 'Out Of Topic Action',
                'model_id': self.env['ir.model']._get_id('res.users'),
                'state': 'code',
                'code': "ai['result'] = 'nope'",
                'use_in_ai': True,
                'ai_tool_description': 'Should not be reachable',
            }
        )
        xml_ids = other_action.get_external_id()
        if xml_id := xml_ids.get(other_action.id):
            tool_name = f'ee_action_{xml_id.split(".")[1]}'
        else:
            tool_name = f'ee_action_action_{other_action.id}'
        tool_env = self.env(
            context={
                **self.env.context,
                'muk_ai_session_agent_id': self.agent.id,
            }
        )
        with self.assertRaises(UserError):
            tool_env['muk_mcp.tool']._call(tool_name, {'msg': 'hi'}, tool_env)

    def test_in_topic_ee_action_runs(self):
        tool_env = self.env(
            context={
                **self.env.context,
                'muk_ai_session_agent_id': self.agent.id,
            }
        )
        text, _info = tool_env['muk_mcp.tool']._call(
            self._ee_tool_name(), {'msg': 'hi'}, tool_env
        )
        self.assertEqual(text, 'echoed: hi')

    def test_ee_action_on_sensitive_model_pauses_for_approval(self):
        self.env['ir.model']._get('res.users').ai_sensitive = True
        sensitive_action = self.env['ir.actions.server'].create(
            {
                'name': 'Sensitive Echo Action',
                'model_id': self.env['ir.model']._get_id('res.users'),
                'state': 'code',
                'code': "ai['result'] = 'echoed: ' + (msg or '')",
                'use_in_ai': True,
                'ai_tool_description': 'Echo on a sensitive model',
                'ai_tool_schema': self.action.ai_tool_schema,
            }
        )
        self.topic.tool_ids = [(4, sensitive_action.id)]
        session = self._make_session()
        tool_name = self._ee_tool_name(sensitive_action)
        with self._patch_provider(
            [
                self._tool_payload(tool_name, {'msg': 'hello'}, 'call_s'),
                self._text_payload('done'),
            ]
        ):
            snapshot = session.start('please echo')
        self.assertEqual(snapshot['state'], 'waiting')
        pending = session.pending_ask or {}
        self.assertEqual(pending.get('kind'), 'approval')
        self.assertEqual(pending.get('name'), tool_name)
        self.assertEqual((pending.get('risk') or {}).get('model'), 'res.users')
        self.assertFalse(
            self.env['muk_mcp.log'].search_count(
                [
                    ('session_id', '=', session.id),
                    ('tool_name', '=', tool_name),
                ]
            ),
            'A paused ee_action_* must not dispatch before approval.',
        )

    def test_ee_action_risk_none_for_non_sensitive_model(self):
        risk = self.env['muk_ai.approval']._assess_risk(self._ee_tool_name(), {})
        self.assertIsNone(risk)

    def test_pinned_foreign_model_record_not_passed(self):
        probe = self.env['ir.actions.server'].create(
            {
                'name': 'Record Probe Action',
                'model_id': self.env['ir.model']._get_id('res.partner'),
                'state': 'code',
                'code': "ai['result'] = {'model': record._name, 'ids': record.ids}",
                'use_in_ai': True,
                'ai_tool_description': 'Report the model of the passed record',
            }
        )
        self.topic.tool_ids = [(4, probe.id)]
        session = self._make_session(
            view_context={
                'kind': 'record',
                'model': 'res.users',
                'id': self.env.user.id,
            }
        )
        tool_env = self.env(
            context={
                **self.env.context,
                'muk_mcp_session_id': session.id,
                'muk_ai_session_agent_id': self.agent.id,
            }
        )
        payload, _info, model = tool_env['muk_mcp.tool']._call_ee_action(
            self._ee_tool_name(probe), {}, tool_env
        )
        result = json.loads(payload)
        self.assertEqual(model, 'res.partner')
        self.assertEqual(result['model'], 'res.partner')
        self.assertEqual(result['ids'], [])

    def test_unpinned_session_gets_empty_recordset_not_user(self):
        probe = self.env['ir.actions.server'].create(
            {
                'name': 'Record Probe Action',
                'model_id': self.env['ir.model']._get_id('res.partner'),
                'state': 'code',
                'code': "ai['result'] = {'model': record._name, 'ids': record.ids}",
                'use_in_ai': True,
                'ai_tool_description': 'Report the model of the passed record',
            }
        )
        self.topic.tool_ids = [(4, probe.id)]
        session = self._make_session()
        tool_env = self.env(
            context={
                **self.env.context,
                'muk_mcp_session_id': session.id,
                'muk_ai_session_agent_id': self.agent.id,
            }
        )
        payload, _info, _model = tool_env['muk_mcp.tool']._call_ee_action(
            self._ee_tool_name(probe), {}, tool_env
        )
        result = json.loads(payload)
        self.assertEqual(result['model'], 'res.partner')
        self.assertEqual(result['ids'], [])

    def test_call_ee_action_next_activity_creates_activity(self):
        todo = self.env.ref('mail.mail_activity_data_todo')
        activity_action = self.env['ir.actions.server'].create(
            {
                'name': 'Schedule Follow-up Action',
                'model_id': self.env['ir.model']._get_id('res.partner'),
                'state': 'next_activity',
                'activity_type_id': todo.id,
                'activity_summary': 'Follow up',
                'use_in_ai': True,
                'ai_tool_description': 'Schedule a follow-up activity',
            }
        )
        self.topic.tool_ids = [(4, activity_action.id)]
        partner = self.env['res.partner'].create({'name': 'Follow-up Lead'})
        session = self._make_session(
            view_context={
                'kind': 'record',
                'model': 'res.partner',
                'id': partner.id,
            }
        )
        tool_env = self.env(
            context={
                **self.env.context,
                'muk_mcp_session_id': session.id,
                'muk_ai_session_agent_id': self.agent.id,
            }
        )
        tool_env['muk_mcp.tool']._call_ee_action(
            self._ee_tool_name(activity_action), {}, tool_env
        )
        activities = self.env['mail.activity'].search(
            [
                ('res_model', '=', 'res.partner'),
                ('res_id', '=', partner.id),
            ]
        )
        self.assertEqual(len(activities), 1)
        self.assertEqual(activities.activity_type_id, todo)
