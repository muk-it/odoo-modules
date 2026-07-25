from __future__ import annotations

from odoo.exceptions import AccessError
from odoo.tests.common import TransactionCase, new_test_user, tagged


@tagged('post_install', '-at_install', 'muk_ai_schedule')
class TestACLUser(TransactionCase):
    """Covers per-user access to schedules and their owned server actions."""

    # ----------------------------------------------------------
    # Setup
    # ----------------------------------------------------------

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.user_a = new_test_user(
            cls.env,
            login='ai_sched_user_a',
            groups='base.group_user',
        )
        cls.user_b = new_test_user(
            cls.env,
            login='ai_sched_user_b',
            groups='base.group_user',
        )
        cls.agent = (
            cls.env['muk_ai.agent']
            .sudo()
            .create(
                {
                    'name': 'Read-only Analyst (test)',
                    'read_only': True,
                },
            )
        )
        cls.Schedule = cls.env['muk_ai.schedule']

    def _vals(self) -> dict:
        """Return the create values for a minimal daily schedule."""
        return {
            'name': 'Sched A',
            'agent_id': self.agent.id,
            'prompt': 'hi',
            'interval_type': 'days',
            'interval_number': 1,
        }

    # ----------------------------------------------------------
    # Tests
    # ----------------------------------------------------------

    def test_user_can_create_own_schedule(self):
        sched = self.Schedule.with_user(self.user_a).create(self._vals())
        self.assertTrue(sched.exists())
        self.assertTrue(sched.action_server_id)
        self.assertTrue(sched.cron_id)

    def test_user_cannot_read_others_schedule(self):
        sched_a = self.Schedule.with_user(self.user_a).create(self._vals())
        self.assertFalse(
            self.Schedule.with_user(self.user_b).search(
                [('id', '=', sched_a.id)],
            )
        )

    def test_user_cannot_write_owned_action(self):
        sched = self.Schedule.with_user(self.user_a).create(self._vals())
        with self.assertRaises(AccessError):
            sched.action_server_id.with_user(self.user_a).write(
                {'name': 'tampered'},
            )

    def test_admin_can_read_all_schedules(self):
        self.Schedule.with_user(self.user_a).create(self._vals())
        admin_count = self.Schedule.sudo().search_count([])
        self.assertGreaterEqual(admin_count, 1)

    def test_user_cannot_author_record_code(self):
        vals = self._vals()
        vals.update(
            record_source='code',
            record_code="records = env['res.partner'].search([])",
        )
        with self.assertRaises(AccessError):
            self.Schedule.with_user(self.user_a).create(vals)

    def test_user_cannot_switch_existing_schedule_to_code(self):
        sched = self.Schedule.with_user(self.user_a).create(self._vals())
        with self.assertRaises(AccessError):
            sched.write(
                {
                    'record_source': 'code',
                    'record_code': "records = env['res.partner'].search([])",
                }
            )

    def test_admin_can_author_record_code(self):
        admin = new_test_user(
            self.env,
            login='ai_sched_admin',
            groups='base.group_user,base.group_system',
        )
        vals = self._vals()
        vals.update(
            record_source='code',
            record_code="records = env['res.partner'].search([])",
        )
        sched = self.Schedule.with_user(admin).create(vals)
        self.assertTrue(sched.exists())
        self.assertEqual(sched.record_source, 'code')
