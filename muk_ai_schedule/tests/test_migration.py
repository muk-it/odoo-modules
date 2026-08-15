from __future__ import annotations

import importlib.util
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

from odoo import models
from odoo.tests.common import tagged

from .common import ScheduleTestCommon

MIGRATIONS = Path(__file__).resolve().parent.parent / 'migrations'


@tagged('post_install', '-at_install', 'muk_ai_schedule')
class TestMigration(ScheduleTestCommon):
    """Covers the owned action/cron migrations replayed on a legacy schedule."""

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    def _load_migration(self, version: str, phase: str) -> Callable:
        """Return the ``migrate`` callable of a versioned migration script."""
        path = MIGRATIONS / version / ('%s-migration.py' % phase)
        spec = importlib.util.spec_from_file_location(
            'muk_ai_schedule_migration_%s_%s' % (version.replace('.', '_'), phase),
            path,
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module.migrate

    def _strip_owned_records(self, schedule: models.BaseModel) -> None:
        """Bring ``schedule`` back to the legacy shape without action or cron."""
        cron = schedule.cron_id.sudo()
        self.env.flush_all()
        self.env.cr.execute(
            'UPDATE muk_ai_schedule SET action_server_id = NULL, cron_id = NULL '
            'WHERE id = %s',
            (schedule.id,),
        )
        self.env.invalidate_all()
        cron.unlink()

    def _write_nextcall_snapshot(
        self,
        schedule: models.BaseModel,
        next_call: datetime,
        last_call: datetime,
    ) -> None:
        """Recreate the pre-migration snapshot table holding the legacy call times."""
        self.addCleanup(
            self.env.cr.execute,
            'DROP TABLE IF EXISTS _muk_ai_schedule_nextcall_snapshot',
        )
        self.env.cr.execute("""
            DROP TABLE IF EXISTS _muk_ai_schedule_nextcall_snapshot;
            CREATE TABLE _muk_ai_schedule_nextcall_snapshot (
                id integer, next_call timestamp, last_call timestamp
            );
        """)
        self.env.cr.execute(
            'INSERT INTO _muk_ai_schedule_nextcall_snapshot VALUES (%s, %s, %s)',
            (schedule.id, next_call, last_call),
        )

    def _replay_provisioning(self, schedule: models.BaseModel) -> None:
        """Strip the owned records of ``schedule`` and replay the 1.0.36 migration."""
        self._strip_owned_records(schedule)
        self._write_nextcall_snapshot(
            schedule,
            datetime(2026, 5, 4, 8, 0),
            datetime(2026, 5, 3, 8, 0),
        )
        self._load_migration('19.0.1.0.36', 'post')(self.env.cr, '19.0.1.0.36')
        self.env.invalidate_all()

    # ----------------------------------------------------------
    # Tests
    # ----------------------------------------------------------

    def test_legacy_schedule_gains_an_owned_action_and_cron(self):
        schedule = self._make_schedule()
        self._replay_provisioning(schedule)
        self.assertEqual(schedule.action_server_id.state, 'ai_agent')
        self.assertEqual(schedule.action_server_id.agent_id, self.agent)
        self.assertEqual(schedule.cron_id.nextcall, datetime(2026, 5, 4, 8, 0))
        self.assertEqual(schedule.cron_id.lastcall, datetime(2026, 5, 3, 8, 0))

    def test_archived_legacy_schedule_gains_an_owned_cron(self):
        schedule = self._make_schedule()
        schedule.write({'active': False})
        self._replay_provisioning(schedule)
        self.assertTrue(schedule.action_server_id)
        self.assertTrue(schedule.cron_id)
        self.assertFalse(schedule.cron_id.active)
        self.assertEqual(schedule.cron_id.nextcall, datetime(2026, 5, 4, 8, 0))

    def test_orphan_session_is_repointed_at_the_owned_action(self):
        schedule = self._make_schedule()
        session = self._make_session(schedule_id=schedule.id)
        session.write({'action_server_id': False})
        self._replay_provisioning(schedule)
        self.assertEqual(session.action_server_id, schedule.action_server_id)

    def test_provisioning_a_schedule_that_already_owns_records_is_a_no_op(self):
        schedule = self._make_schedule()
        action_id, cron_id = schedule.action_server_id.id, schedule.cron_id.id
        schedule._provision_owned_action()
        self.assertEqual(schedule.action_server_id.id, action_id)
        self.assertEqual(schedule.cron_id.id, cron_id)

    def test_legacy_agent_state_is_repointed_to_ai_agent(self):
        schedule = self._make_schedule()
        action = schedule.action_server_id.sudo()
        self.env.cr.execute(
            "UPDATE ir_act_server SET state = 'agent' WHERE id = %s",
            (action.id,),
        )
        self.env.invalidate_all()
        self._load_migration('19.0.1.0.37', 'post')(self.env.cr, '19.0.1.0.37')
        self.env.invalidate_all()
        self.assertEqual(action.state, 'ai_agent')
