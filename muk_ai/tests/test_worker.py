from __future__ import annotations

from datetime import datetime

from odoo import Command, api, models
from odoo.tests import tagged
from odoo.tests.common import new_test_user

from odoo.addons.muk_ai.tests.common import AITestCommon


@tagged('post_install', '-at_install', 'muk_ai')
class TestSessionWorker(AITestCommon):
    """Verify the cron worker sweep, its dispatch, and context restoration."""

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    def _pending_session(self, name: str = 'queued') -> models.Model:
        """Create a session queued in the running state with a user turn."""
        session = self.env['muk_ai.session'].create({'name': name})
        session.write(
            {
                'state': 'running',
                'conversation': [
                    {'role': 'user', 'content': [{'type': 'input_text', 'text': 'go'}]}
                ],
            }
        )
        return session

    def _text_payload(self, text: str = 'worker answer') -> dict:
        """Build a provider payload emitting plain assistant text."""
        return {
            'text': text,
            'tool_calls': [],
            'carry_inputs': [
                {
                    'type': 'message',
                    'content': [{'type': 'output_text', 'text': text}],
                }
            ],
            'usage': {'input_tokens': 3, 'output_tokens': 1},
        }

    def _worker_action(self, name: str = 'AI worker') -> models.Model:
        """Create the server action wired to the AI session worker state."""
        return self.env['ir.actions.server'].create(
            {
                'name': name,
                'model_id': self.env['ir.model']._get_id('muk_ai.session'),
                'state': 'ai_session',
            }
        )

    # ----------------------------------------------------------
    # Tests: user context capture and restoration
    # ----------------------------------------------------------

    def test_captured_context_keeps_json_safe_values_only(self):
        session = self.env['muk_ai.session'].create({'name': 'context'})
        captured = session.with_context(
            lang='en_US',
            tz='Europe/Vienna',
            allowed_company_ids=[self.env.company.id],
            stamp=datetime(2026, 1, 1),
            owner=self.env.user,
        )._capture_user_context()
        self.assertEqual(captured['lang'], 'en_US')
        self.assertEqual(captured['tz'], 'Europe/Vienna')
        self.assertEqual(captured['allowed_company_ids'], [self.env.company.id])
        self.assertNotIn('stamp', captured)
        self.assertNotIn('owner', captured)

    def test_captured_context_restores_the_owning_company(self):
        company = self.env['res.company'].create({'name': 'Worker Branch'})
        user = new_test_user(self.env, login='ai_worker_co', groups='base.group_user')
        user.write({'company_ids': [Command.link(company.id)]})
        session = (
            self.env['muk_ai.session']
            .with_user(user)
            .with_context(allowed_company_ids=[company.id])
            .create({'name': 'branch turn'})
        )
        session._trigger_worker()
        stored = session.sudo().user_context
        self.assertEqual(stored['allowed_company_ids'], [company.id])
        restored = api.Environment(self.env.cr, user.id, stored)
        self.assertEqual(restored.company, company)
        self.assertEqual(restored.companies, company)

    # ----------------------------------------------------------
    # Tests: pending session lookup
    # ----------------------------------------------------------

    def test_only_running_and_compacting_sessions_are_pending(self):
        sessions = {}
        for state in ('new', 'running', 'compacting', 'waiting', 'stopped', 'error'):
            session = self.env['muk_ai.session'].create({'name': f'state-{state}'})
            session.state = state
            sessions[state] = session
        self.env.flush_all()
        pending = set(self.env['muk_ai.session']._find_pending_session_ids(limit=100))
        picked = {state for state, s in sessions.items() if s.id in pending}
        self.assertEqual(picked, {'running', 'compacting'})

    def test_pending_lookup_ignores_session_ownership(self):
        user = new_test_user(
            self.env, login='ai_worker_other', groups='base.group_user'
        )
        session = self._pending_session('other-owner')
        session.sudo().user_id = user
        self.env.flush_all()
        pending = self.env['muk_ai.session']._find_pending_session_ids(limit=100)
        self.assertIn(session.id, pending)

    def test_pending_lookup_is_capped_by_the_active_worker_count(self):
        crons = self.env['muk_ai.session']._session_worker_crons()
        self.assertTrue(crons)
        crons.write({'active': False})
        for index in range(3):
            self._pending_session(f'capped-{index}')
        self.env.flush_all()
        self.assertEqual(self.env['muk_ai.session']._active_worker_count(), 1)
        self.assertEqual(len(self.env['muk_ai.session']._find_pending_session_ids()), 1)
        crons[:2].write({'active': True})
        self.assertEqual(self.env['muk_ai.session']._active_worker_count(), 2)
        self.assertEqual(len(self.env['muk_ai.session']._find_pending_session_ids()), 2)

    # ----------------------------------------------------------
    # Tests: worker failure handling
    # ----------------------------------------------------------

    def test_marking_a_session_in_error_closes_it_out(self):
        session = self._pending_session('worker-error')
        session.conversation = [
            *session.conversation,
            {
                'type': 'function_call',
                'name': 'list_modules',
                'arguments': '{}',
                'call_id': 'orphan_c1',
            },
        ]
        self.env.flush_all()
        with self.enter_registry_test_mode():
            self.env['muk_ai.session']._mark_session_error(session.id, 'provider down')
        self.assertEqual(session.state, 'error')
        self.assertEqual(session.error_message, 'provider down')
        self.assertNotIn(
            session.id,
            self.env['muk_ai.session']._find_pending_session_ids(limit=100),
        )
        outputs = [
            item
            for item in session.conversation
            if item.get('type') == 'function_call_output'
        ]
        self.assertEqual(len(outputs), 1)
        self.assertIn('provider down', outputs[0]['output'])

    # ----------------------------------------------------------
    # Tests: cron entrypoint
    # ----------------------------------------------------------

    def test_cron_runs_a_queued_session_to_completion(self):
        session = self._pending_session('cron-run')
        self.env.flush_all()
        with (
            self.enter_registry_test_mode(),
            self._mock_responses([self._text_payload()]),
        ):
            self.env['muk_ai.session']._cron_run_pending_sessions()
        self.assertEqual(session.state, 'done')
        self.assertEqual(session.last_text, 'worker answer')

    def test_cron_leaves_a_settled_session_alone(self):
        session = self.env['muk_ai.session'].create({'name': 'cron-idle'})
        session.write(
            {
                'state': 'done',
                'conversation': [
                    {'role': 'user', 'content': [{'type': 'input_text', 'text': 'go'}]}
                ],
            }
        )
        conversation = list(session.conversation)
        self.env.flush_all()
        with self.enter_registry_test_mode(), self._mock_responses([]):
            self.env['muk_ai.session']._cron_run_pending_sessions()
        self.assertEqual(session.state, 'done')
        self.assertEqual(list(session.conversation), conversation)

    # ----------------------------------------------------------
    # Tests: server action dispatch
    # ----------------------------------------------------------

    def test_server_action_drains_the_pending_queue(self):
        action = self._worker_action()
        session = self._pending_session('action-multi')
        self.env.flush_all()
        with (
            self.enter_registry_test_mode(),
            self._mock_responses([self._text_payload('action answer')]),
        ):
            action.run()
        self.assertEqual(session.state, 'done')
        self.assertEqual(session.last_text, 'action answer')

    def test_single_record_server_action_drains_the_pending_queue(self):
        action = self._worker_action('AI worker single')
        session = self._pending_session('action-single')
        self.env.flush_all()
        with (
            self.enter_registry_test_mode(),
            self._mock_responses([self._text_payload('single answer')]),
        ):
            action._run_action_ai_session()
        self.assertEqual(session.state, 'done')
        self.assertEqual(session.last_text, 'single answer')
