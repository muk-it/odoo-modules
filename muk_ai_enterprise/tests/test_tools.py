from __future__ import annotations

import json
from unittest.mock import patch

import psycopg2

from odoo import models
from odoo.api import Environment
from odoo.exceptions import UserError
from odoo.tests.common import tagged

from .common import BridgeTestCommon

PROBE_CODE = "ai['result'] = {'model': record._name, 'ids': record.ids}"


@tagged('post_install', '-at_install', 'muk_ai_enterprise')
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

    def _ee_tool_name(self, action: models.BaseModel | None = None) -> str:
        """Return the ``ee_action_*`` tool name for a server action.

        :param action: the action to name; defaults to the fixture action
        """
        action = action if action is not None else self.action
        xml_ids = action.get_external_id()
        if xml_id := xml_ids.get(action.id):
            return f'ee_action_{xml_id.split(".")[1]}'
        return f'ee_action_action_{action.id}'

    def _make_session(self, **vals) -> models.BaseModel:
        """Create a session bound to the fixture agent.

        :param vals: extra values merged into the session defaults
        :return: the created ``muk_ai.session`` record
        """
        defaults = {'name': 'EE Tool Session', 'agent_id': self.agent.id}
        defaults.update(vals)
        return self.env['muk_ai.session'].create(defaults)

    def _tool_env(self, session: models.BaseModel | None = None) -> Environment:
        """Return an env carrying the EE dispatch context markers.

        :param session: the session to pin, or ``None`` for agent-only context
        :return: an environment with the muk_ai/muk_mcp context keys set
        """
        context = {**self.env.context, 'muk_ai_session_agent_id': self.agent.id}
        if session is not None:
            context['muk_mcp_session_id'] = session.id
        return self.env(context=context)

    def _make_ai_action(
        self,
        name: str,
        code: str = "ai['result'] = 'ok'",
        model: str = 'res.partner',
        use_in_ai: bool = True,
    ) -> models.BaseModel:
        """Create a code server action on ``model``.

        :param name: the action name
        :param code: the safe_eval body of the action
        :param model: the technical name of the action's target model
        :param use_in_ai: whether the action is exposed to the agent
        :return: the created ``ir.actions.server`` record
        """
        return self.env['ir.actions.server'].create(
            {
                'name': name,
                'model_id': self.env['ir.model']._get_id(model),
                'state': 'code',
                'code': code,
                'use_in_ai': use_in_ai,
                'ai_tool_description': name,
            }
        )

    def _add_xml_id(self, module: str, name: str, action: models.BaseModel) -> None:
        """Give a server action an extra external id.

        :param module: the module part of the external id
        :param name: the technical part of the external id
        :param action: the server action receiving the external id
        """
        self.env['ir.model.data'].create(
            {
                'module': module,
                'name': name,
                'model': 'ir.actions.server',
                'res_id': action.id,
            }
        )
        self.addCleanup(self.env.registry.clear_cache)

    def _resolved_record(self, view_context: dict | None) -> models.BaseModel:
        """Resolve the EE record of a session carrying ``view_context``.

        :param view_context: the session view context, or ``None`` for none
        :return: the resolved record, or the session env's user
        """
        vals = {} if view_context is None else {'view_context': view_context}
        tool_env = self._tool_env(self._make_session(**vals))
        return tool_env['muk_mcp.tool']._resolve_ee_record(tool_env)

    # ----------------------------------------------------------
    # Tests catalog
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
        ee_name = self._ee_tool_name()
        for registry in ('odoo', 'mcp'):
            names = {t['name'] for t in Tool.get_tools(registry=registry)}
            self.assertNotIn(ee_name, names, f'leaked into the {registry} registry')

    def test_ee_tools_reach_the_catalog_only_through_the_odoo_registry(self):
        Tool = self._tool_env()['muk_mcp.tool']
        odoo_names = {t['name'] for t in Tool.get_tools(registry='odoo')}
        self.assertIn(self._ee_tool_name(), odoo_names)

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

    # ----------------------------------------------------------
    # Tests _resolve_ee_action
    # ----------------------------------------------------------

    def test_resolve_ee_action_by_database_id(self):
        Tool = self.env['muk_mcp.tool']
        self.assertEqual(
            Tool._resolve_ee_action(f'ee_action_action_{self.action.id}'),
            self.action,
        )
        plain = self._make_ai_action('Not For AI', use_in_ai=False)
        self.assertFalse(Tool._resolve_ee_action(f'ee_action_action_{plain.id}'))
        self.assertFalse(Tool._resolve_ee_action('ee_action_action_99999999'))

    def test_resolve_ee_action_ignores_foreign_tool_names(self):
        Tool = self.env['muk_mcp.tool']
        resolved = Tool._resolve_ee_action('search_read')
        self.assertFalse(resolved)
        self.assertEqual(resolved._name, 'ir.actions.server')

    def test_resolve_ee_action_tie_break_prefers_the_lowest_id(self):
        first = self._make_ai_action('First Shared Action')
        second = self._make_ai_action('Second Shared Action')
        self.assertLess(first.id, second.id)
        self._add_xml_id('zz_muk_ai_ee_test', 'shared_echo', first)
        self._add_xml_id('aa_muk_ai_ee_test', 'shared_echo', second)
        resolved = self.env['muk_mcp.tool']._resolve_ee_action('ee_action_shared_echo')
        self.assertEqual(resolved, first)

    # ----------------------------------------------------------
    # Tests _resolve_ee_record
    # ----------------------------------------------------------

    def test_resolve_ee_record_returns_the_pinned_record(self):
        partner = self.env['res.partner'].create({'name': 'Pinned Partner'})
        resolved = self._resolved_record(
            {'kind': 'record', 'model': 'res.partner', 'id': partner.id}
        )
        self.assertEqual(resolved, partner)

    def test_resolve_ee_record_degrades_to_the_user(self):
        partner = self.env['res.partner'].create({'name': 'Doomed Partner'})
        dead_id = partner.id
        partner.unlink()
        for view_context in (
            None,
            {'kind': 'list', 'model': 'res.partner'},
            {'kind': 'record', 'model': 'no.such.model', 'id': 1},
            {'kind': 'record', 'model': 'res.partner', 'id': 'not-an-int'},
            {'kind': 'record', 'model': 'res.partner', 'id': dead_id},
            {'kind': 'record', 'id': 1},
        ):
            with self.subTest(view_context=view_context):
                self.assertEqual(self._resolved_record(view_context), self.env.user)

    # ----------------------------------------------------------
    # Tests dispatch
    # ----------------------------------------------------------

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

    def test_unknown_ee_action_raises(self):
        Tool = self.env['muk_mcp.tool']
        with self.assertRaises(UserError):
            Tool._call('ee_action_does_not_exist', {}, self.env)

    def test_out_of_topic_ee_action_rejected(self):
        other_action = self._make_ai_action('Out Of Topic Action', model='res.users')
        tool_env = self._tool_env()
        with self.assertRaises(UserError):
            tool_env['muk_mcp.tool']._call(
                self._ee_tool_name(other_action), {'msg': 'hi'}, tool_env
            )

    def test_in_topic_ee_action_runs(self):
        tool_env = self._tool_env()
        text, _info = tool_env['muk_mcp.tool']._call(
            self._ee_tool_name(), {'msg': 'hi'}, tool_env
        )
        self.assertEqual(text, 'echoed: hi')

    # ----------------------------------------------------------
    # Tests error handling
    # ----------------------------------------------------------

    def test_generic_action_failure_is_wrapped_in_a_user_error(self):
        boom = self._make_ai_action('Boom Action', code="ai['result'] = 1 / 0")
        self.topic.tool_ids = [(4, boom.id)]
        tool_env = self._tool_env()
        with self.assertRaises(UserError) as error:
            tool_env['muk_mcp.tool']._call_ee_action(
                self._ee_tool_name(boom), {}, tool_env
            )
        message = str(error.exception)
        self.assertIn(self._ee_tool_name(boom), message)
        self.assertIn('failed', message)

    def test_serialization_failure_is_re_raised_for_retry(self):
        tool_env = self._tool_env()
        with patch.object(
            type(self.env['ir.actions.server']),
            '_ai_tool_run',
            autospec=True,
            side_effect=psycopg2.errors.SerializationFailure('concurrent update'),
        ):
            with self.assertRaises(psycopg2.errors.SerializationFailure):
                tool_env['muk_mcp.tool']._call_ee_action(
                    self._ee_tool_name(), {'msg': 'hi'}, tool_env
                )

    # ----------------------------------------------------------
    # Tests approval
    # ----------------------------------------------------------

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

    # ----------------------------------------------------------
    # Tests record binding
    # ----------------------------------------------------------

    def test_pinned_foreign_model_record_not_passed(self):
        probe = self._make_ai_action('Record Probe Action', code=PROBE_CODE)
        self.topic.tool_ids = [(4, probe.id)]
        session = self._make_session(
            view_context={
                'kind': 'record',
                'model': 'res.users',
                'id': self.env.user.id,
            }
        )
        tool_env = self._tool_env(session)
        payload, _info, model = tool_env['muk_mcp.tool']._call_ee_action(
            self._ee_tool_name(probe), {}, tool_env
        )
        result = json.loads(payload)
        self.assertEqual(model, 'res.partner')
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
        tool_env = self._tool_env(session)
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
