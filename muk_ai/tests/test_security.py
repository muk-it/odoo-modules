from __future__ import annotations

from unittest.mock import patch

from odoo.exceptions import AccessError, UserError
from odoo.tests import new_test_user

from odoo.addons.muk_ai.tests.common import AITestCommon
from odoo.addons.muk_mcp.tests.common import MCPHttpCase


class TestSecurity(AITestCommon):
    """Verify the record rules, the agent rights, the rate limit and foreign calls."""

    # ----------------------------------------------------------
    # Setup
    # ----------------------------------------------------------

    @classmethod
    def setUpClass(cls) -> None:
        """Create two users and a manager."""
        super().setUpClass()
        cls.user_a = new_test_user(cls.env, login='ai_user_a')
        cls.user_b = new_test_user(cls.env, login='ai_user_b')
        cls.manager = new_test_user(
            cls.env, login='ai_manager', groups='base.group_system'
        )

    # ----------------------------------------------------------
    # Tests
    # ----------------------------------------------------------

    def test_record_rules_keep_each_users_records_to_themselves(self):
        records = {}
        for user in (self.user_a, self.user_b):
            session = (
                self.env['muk_ai.session'].with_user(user).create({'name': user.login})
            )
            records[user] = {
                'muk_ai.session': session,
                'muk_ai.session.event': self.env['muk_ai.session.event'].create(
                    {
                        'session_id': session.id,
                        'kind': 'text',
                        'payload': {'kind': 'text', 'content': 'hi'},
                    }
                ),
                'muk_ai.session.pending': self.env['muk_ai.session.pending'].create(
                    {'session_id': session.id, 'content': 'queued'}
                ),
                'muk_ai.approval': self.env['muk_ai.approval'].create(
                    {
                        'session_id': session.id,
                        'user_id': user.id,
                        'decision': 'approved',
                        'tool_name': 'update_records',
                    }
                ),
                'muk_ai.space': self.env['muk_ai.space'].create(
                    {'name': user.login, 'user_id': user.id}
                ),
            }
        system = self.env['muk_ai.space'].create(
            {'name': 'Everyone', 'user_id': False, 'domain': "[('id', '>', 0)]"}
        )
        for model in records[self.user_a]:
            shared = system if model == 'muk_ai.space' else self.env[model]
            own_a, own_b = records[self.user_a][model], records[self.user_b][model]
            for user, visible in (
                (self.user_a, own_a | shared),
                (self.user_b, own_b | shared),
                (self.manager, own_a | own_b | shared),
            ):
                with self.subTest(model=model, user=user.login):
                    found = (
                        self.env[model]
                        .with_user(user)
                        .search([('id', 'in', (own_a | own_b | shared).ids)])
                    )
                    self.assertEqual(sorted(found.ids), sorted(visible.ids))

    def test_only_a_manager_edits_an_agent(self):
        agent = self.env['muk_ai.agent'].create({'name': 'Read only'})
        self.assertEqual(
            agent.with_user(self.user_a).read(['name'])[0]['name'], 'Read only'
        )
        with self.assertRaises(AccessError):
            agent.with_user(self.user_a).write({'name': 'Hacked'})
        agent.with_user(self.manager).write({'name': 'Updated'})
        self.assertEqual(agent.name, 'Updated')

    def test_the_rate_limit_caps_the_chats_started_per_minute(self):
        self.provider.rate_limit = 3
        sessions = self.env['muk_ai.session'].with_user(self.user_a)
        sessions.create([{'name': 'one'}, {'name': 'two'}])
        with self.assertRaisesRegex(
            UserError,
            r'the limit for new chats is 3 per minute\. You started 2 in the last '
            r'minute and asked for 2 more\.',
        ):
            sessions.create([{'name': 'three'}, {'name': 'four'}])
        sessions.create({'name': 'three'})
        with self.assertRaises(UserError):
            sessions.create({'name': 'four'})
        other = self.env['muk_ai.session'].with_user(self.user_b).create({'name': 'b'})
        self.assertEqual(other.user_id, self.user_b)

    def test_a_foreign_chat_refuses_every_call(self):
        session = (
            self.env['muk_ai.session'].with_user(self.user_a).create({'name': 'A'})
        )
        foreign = session.with_user(self.user_b)
        for name, call in (
            ('fetch_events', foreign.fetch_events),
            ('get_snapshot', foreign.get_snapshot),
            ('discard_attachments', lambda: foreign.discard_attachments([1])),
            ('action_open', foreign.action_open),
            ('action_stop', foreign.action_stop),
            ('action_handover', lambda: foreign.action_handover(self.user_b.id)),
        ):
            with self.subTest(name), self.assertRaises(AccessError):
                call()
        self.assertEqual(
            session.with_user(self.manager).action_stop()['state'], 'stopped'
        )


class TestSessionBinding(MCPHttpCase):
    """Verify a tool call never binds itself to a chat its caller may not steer."""

    # ----------------------------------------------------------
    # Setup
    # ----------------------------------------------------------

    @classmethod
    def setUpClass(cls) -> None:
        """Create a chat owner and two agents that allow handoff."""
        super().setUpClass()
        cls.owner = new_test_user(cls.env, login='binding_owner')
        agents = cls.env['muk_ai.agent']
        cls.coordinator = agents.create(
            {'name': 'Binding Coordinator', 'allow_handoff': True}
        )
        cls.target = agents.create({'name': 'Binding Target', 'allow_handoff': True})
        sessions = cls.env['muk_ai.session'].with_user(cls.owner)
        cls.chat = sessions.create({'name': 'chat', 'agent_id': cls.coordinator.id})
        cls.other = sessions.create({'name': 'other', 'agent_id': cls.coordinator.id})

    # ----------------------------------------------------------
    # Tests
    # ----------------------------------------------------------

    def test_an_mcp_client_cannot_switch_the_agent_of_a_foreign_chat(self):
        result = self.mcp_tool(
            'switch_agent',
            {'agent': self.target.id, 'context': {'muk_mcp_session_id': self.chat.id}},
        )
        self.assertEqual(self.chat.agent_id, self.coordinator)
        self.assertTrue(result.get('isError'))

    def test_a_tool_argument_cannot_rebind_the_chat(self):
        call = {
            'call_id': 'c1',
            'name': 'switch_agent',
            'arguments': {
                'agent': self.target.id,
                'context': {'muk_mcp_session_id': self.other.id},
            },
        }
        payloads = [
            {'text': '', 'tool_calls': [call], 'carry_inputs': [], 'usage': {}},
            {'text': 'done', 'tool_calls': [], 'carry_inputs': [], 'usage': {}},
        ]
        with patch.object(
            type(self.env['muk_ai.provider']),
            '_request_responses',
            autospec=True,
            side_effect=lambda *args, **kwargs: payloads.pop(0),
        ):
            self.chat.with_user(self.owner).send_message('route me')
        self.assertEqual(self.chat.agent_id, self.target)
        self.assertEqual(self.other.agent_id, self.coordinator)
