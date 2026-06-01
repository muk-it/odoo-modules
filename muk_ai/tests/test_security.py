from odoo.exceptions import AccessError, UserError
from odoo.tests.common import TransactionCase, new_test_user


class TestAiSecurity(TransactionCase):

    # ----------------------------------------------------------
    # Setup
    # ----------------------------------------------------------

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.user_a = new_test_user(
            cls.env, login='ai_user_a', groups='base.group_user',
        )
        cls.user_b = new_test_user(
            cls.env, login='ai_user_b', groups='base.group_user',
        )
        cls.manager = new_test_user(
            cls.env, login='ai_manager', groups='base.group_system',
        )

    # ----------------------------------------------------------
    # Tests
    # ----------------------------------------------------------

    def test_user_sees_own_sessions_only(self):
        session_a = self.env['muk_ai.session'].with_user(self.user_a).create(
            {'name': 'A session'}
        )
        self.env['muk_ai.session'].with_user(self.user_b).create(
            {'name': 'B session'}
        )
        visible_to_a = self.env['muk_ai.session'].with_user(self.user_a).search(
            [('name', 'in', ('A session', 'B session'))]
        )
        self.assertEqual(visible_to_a, session_a)

    def test_manager_sees_all_sessions(self):
        self.env['muk_ai.session'].with_user(self.user_a).create(
            {'name': 'A session'}
        )
        self.env['muk_ai.session'].with_user(self.user_b).create(
            {'name': 'B session'}
        )
        visible = self.env['muk_ai.session'].with_user(self.manager).search(
            [('name', 'in', ('A session', 'B session'))]
        )
        self.assertEqual(len(visible), 2)

    def test_agent_write_requires_manager(self):
        agent = self.env['muk_ai.agent'].create({'name': 'Read only'})
        with self.assertRaises(AccessError):
            agent.with_user(self.user_a).write({'name': 'Hacked'})
        agent.with_user(self.manager).write({'name': 'Updated'})
        self.assertEqual(agent.name, 'Updated')

    def test_rate_limit_blocks_excessive_creates(self):
        provider = self.env.ref('muk_ai.provider_openai').sudo()
        provider.write({'rate_limit': 2})
        self.env.company.default_ai_provider_id = provider
        Session = self.env['muk_ai.session'].with_user(self.user_a)
        Session.create({'name': 's1'})
        Session.create({'name': 's2'})
        with self.assertRaises(UserError):
            Session.create({'name': 's3'})
