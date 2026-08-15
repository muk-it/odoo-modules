from __future__ import annotations

from odoo import models
from odoo.exceptions import AccessError, UserError
from odoo.tests.common import new_test_user, tagged

from .common import ScheduleTestCommon


@tagged('post_install', '-at_install', 'muk_ai_schedule')
class TestACLUser(ScheduleTestCommon):
    """Covers per-user access to schedules and their owned server actions."""

    # ----------------------------------------------------------
    # Setup
    # ----------------------------------------------------------

    @classmethod
    def setUpClass(cls) -> None:
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

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    def _make_admin(self) -> models.BaseModel:
        """Return a system administrator test user.

        :return: a ``res.users`` record in ``base.group_system``
        """
        return new_test_user(
            self.env,
            login='ai_sched_admin',
            groups='base.group_user,base.group_system',
        )

    # ----------------------------------------------------------
    # Tests
    # ----------------------------------------------------------

    def test_user_can_create_own_schedule(self):
        sched = self.Schedule.with_user(self.user_a).create(self._schedule_vals())
        self.assertTrue(sched.exists())
        self.assertTrue(sched.action_server_id)
        self.assertTrue(sched.cron_id)

    def test_user_cannot_read_others_schedule(self):
        sched_a = self.Schedule.with_user(self.user_a).create(self._schedule_vals())
        self.assertFalse(
            self.Schedule.with_user(self.user_b).search(
                [('id', '=', sched_a.id)],
            )
        )

    def test_user_cannot_write_owned_action(self):
        sched = self.Schedule.with_user(self.user_a).create(self._schedule_vals())
        with self.assertRaises(AccessError):
            sched.action_server_id.with_user(self.user_a).write(
                {'name': 'tampered'},
            )

    def test_user_cannot_author_record_code(self):
        vals = self._schedule_vals()
        vals.update(
            record_source='code',
            record_code="records = env['res.partner'].search([])",
        )
        with self.assertRaises(AccessError):
            self.Schedule.with_user(self.user_a).create(vals)

    def test_user_cannot_switch_existing_schedule_to_code(self):
        sched = self.Schedule.with_user(self.user_a).create(self._schedule_vals())
        with self.assertRaises(AccessError):
            sched.write(
                {
                    'record_source': 'code',
                    'record_code': "records = env['res.partner'].search([])",
                }
            )

    def test_user_cannot_write_record_code_while_source_stays_domain(self):
        sched = self.Schedule.with_user(self.user_a).create(self._schedule_vals())
        with self.assertRaises(AccessError):
            sched.write({'record_code': "records = env['res.partner'].search([])"})

    def test_user_cannot_copy_a_code_schedule_they_own(self):
        admin = self._make_admin()
        vals = self._schedule_vals()
        vals.update(
            user_id=self.user_a.id,
            record_source='code',
            record_code="records = env['res.partner'].search([])",
        )
        sched = self.Schedule.with_user(admin).create(vals)
        self.assertTrue(sched.with_user(self.user_a).exists())
        with self.assertRaises(AccessError):
            sched.with_user(self.user_a).copy()

    def test_archived_owner_schedule_does_not_escalate_to_admin(self):
        schedule = self.Schedule.with_user(self.user_a).create(self._schedule_vals())
        self.user_a.sudo().active = False
        with self._mock_provider(), self.assertRaises(UserError):
            schedule.sudo().action_fire_now()
        self.assertFalse(
            self.env['muk_ai.session'].search([('schedule_id', '=', schedule.id)]),
        )

    def test_admin_can_author_record_code(self):
        admin = self._make_admin()
        vals = self._schedule_vals()
        vals.update(
            record_source='code',
            record_code="records = env['res.partner'].search([])",
        )
        sched = self.Schedule.with_user(admin).create(vals)
        self.assertEqual(
            sched.action_server_id.sudo().agent_record_code,
            vals['record_code'],
        )
