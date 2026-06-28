from odoo.tests.common import TransactionCase, tagged


@tagged('post_install', '-at_install', 'muk_ai_schedule')
class TestMigration(TransactionCase):
    """Covers that every schedule owns an action and cron post-migration."""

    # ----------------------------------------------------------
    # Tests
    # ----------------------------------------------------------

    def test_all_schedules_have_owned_action(self):
        for sched in self.env['muk_ai.schedule'].sudo().search([]):
            self.assertTrue(
                sched.action_server_id,
                'schedule %s missing action' % sched.name,
            )
            self.assertTrue(
                sched.cron_id,
                'schedule %s missing cron' % sched.name,
            )
            self.assertEqual(sched.action_server_id.state, 'ai_agent')

    def test_provision_is_idempotent(self):
        sched = self.env['muk_ai.schedule'].sudo().search([], limit=1)
        if not sched:
            self.skipTest('no schedules to test')
        action_id_before = sched.action_server_id.id
        cron_id_before = sched.cron_id.id
        sched._provision_owned_action()
        self.assertEqual(sched.action_server_id.id, action_id_before)
        self.assertEqual(sched.cron_id.id, cron_id_before)
