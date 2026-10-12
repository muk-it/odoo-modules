from __future__ import annotations

from odoo.exceptions import UserError
from odoo.tests.common import new_test_user, tagged

from .common import AutomationTestCommon
from odoo.addons.muk_ai_automation.tools.constants import MAX_PROMPT_CHARS
from odoo.addons.muk_ai_automation.tools.dispatch import (
    PreviousProxy,
    _build_prompt,
    _create_session,
    _resolve_records,
    _resolve_target_model,
    _spawn_user,
)


@tagged('post_install', '-at_install', 'muk_ai_automation')
class TestDispatchHelper(AutomationTestCommon):
    """Test the dispatch helper functions in isolation."""

    @classmethod
    def setUpClass(cls) -> None:
        """Add the partners the record resolvers select from."""
        super().setUpClass()
        cls.partners = cls._make_partners(4, prefix='Helper Partner')

    # ----------------------------------------------------------
    # Tests Record Resolution
    # ----------------------------------------------------------

    def test_resolve_records_via_domain(self):
        target = self.partners[:2]
        action = self._make_action(agent_record_domain=self._domain_for(target))
        records = _resolve_records(action, {})
        self.assertEqual(sorted(records.ids), sorted(target.ids))

    def test_resolve_records_via_code(self):
        action = self._make_action(
            agent_record_source='code',
            agent_record_code='records = env["res.partner"].search([], limit=2)',
        )
        records = _resolve_records(action, {})
        self.assertEqual(records._name, 'res.partner')
        self.assertEqual(len(records), 2)

    def test_resolve_records_invalid_code_returns_empty(self):
        action = self._make_action(
            agent_record_source='code',
            agent_record_code='this is not valid python <<<',
        )
        records = _resolve_records(action, {})
        self.assertEqual(len(records), 0)
        self.assertEqual(records._name, 'res.partner')

    def test_resolve_records_invalid_domain_returns_empty(self):
        action = self._make_action(agent_record_domain="[('id', '=',")
        records = _resolve_records(action, {})
        self.assertEqual(len(records), 0)
        self.assertEqual(records._name, 'res.partner')

    def test_resolve_records_without_target_model_is_empty(self):
        action = self.env['ir.actions.server'].new(self._action_vals(model_id=False))
        self.assertIsNone(_resolve_target_model(action, {}))
        self.assertEqual(len(_resolve_records(action, {})), 0)

    # ----------------------------------------------------------
    # Tests Previous Session Proxy
    # ----------------------------------------------------------

    def test_previous_proxy_with_no_session(self):
        proxy = PreviousProxy(None)
        self.assertEqual(proxy.last_text, '')
        self.assertEqual(proxy.tool_log, [])

    def test_previous_proxy_tool_log_with_logged_session(self):
        session = self.env['muk_ai.session'].create({'name': 'Logged Session'})
        self.env['muk_mcp.log'].sudo().create(
            {
                'tool_name': 'search',
                'request_data': '{"model": "res.partner"}',
                'response_data': '{"ids": [1]}',
                'session_id': session.id,
                'source': 'chat',
            }
        )
        log = PreviousProxy(session).tool_log
        self.assertEqual(len(log), 1)
        self.assertEqual(log[0]['name'], 'search')
        self.assertEqual(log[0]['arguments'], {'model': 'res.partner'})
        self.assertEqual(log[0]['output'], {'ids': [1]})

    # ----------------------------------------------------------
    # Tests Prompt Building
    # ----------------------------------------------------------

    def test_build_prompt_truncates_an_oversized_render(self):
        action = self._make_action(agent_prompt='{{ "x" * 5000 }}')
        empty = self.env['base'].browse([])
        prompt, render_err = _build_prompt(
            action,
            record=empty,
            records=empty,
            previous_session=None,
        )
        self.assertIsNone(render_err)
        self.assertTrue(prompt.startswith('x' * MAX_PROMPT_CHARS))
        self.assertEqual(prompt.count('x'), MAX_PROMPT_CHARS)
        self.assertIn('prompt truncated', prompt)

    # ----------------------------------------------------------
    # Tests Session Creation
    # ----------------------------------------------------------

    def test_create_session_writes_action_server_id(self):
        action = self._make_action()
        with self._mock_provider():
            session = _create_session(action, 'Hello.', None)
        self.assertEqual(session.action_server_id, action)
        self.assertEqual(session.agent_id, self.agent)

    def test_chats_run_as_the_runner_unless_a_rule_sets_the_user(self):
        runner, rule_user = (
            new_test_user(self.env, login=login, groups='base.group_system')
            for login in ('automation_runner', 'automation_rule_user')
        )
        action = self._make_action()
        self.assertEqual(_spawn_user(action), self.env.ref('base.user_admin'))
        with self._mock_provider():
            action.with_user(runner).run()
        self.env['base.automation'].create(
            {
                'name': 'Rule',
                'model_id': action.model_id.id,
                'trigger': 'on_create',
                'action_server_ids': [(6, 0, action.ids)],
                'agent_user_id': rule_user.id,
            }
        )
        with self._mock_provider():
            action.with_user(runner).run()
        self.assertEqual(
            self._sessions_of(action).user_id.ids, [runner.id, rule_user.id]
        )
        rule_user.active = False
        with self._mock_provider(), self.assertRaises(UserError):
            action.with_user(runner).run()
        self.assertEqual(len(self._sessions_of(action)), 2)
