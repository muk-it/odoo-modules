from __future__ import annotations

import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from unittest.mock import MagicMock, patch

from odoo import fields, models
from odoo.tests import common, tagged
from odoo.tools import SQL


@tagged('post_install', '-at_install')
class TestMcpGarbageCollection(common.TransactionCase):
    """Cover the autovacuum hooks collecting logs, sessions and notifications."""

    # ----------------------------------------------------------
    # Setup
    # ----------------------------------------------------------

    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls.log_model = cls.env['muk_mcp.log']
        cls.session_model = cls.env['muk_mcp.session']
        cls.notification_model = cls.env['muk_mcp.notification']
        cls.config = cls.env['ir.config_parameter'].sudo()

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    def _backdate(self, records: models.BaseModel, days: int) -> None:
        """Move the creation date of ``records`` ``days`` into the past.

        ``create_date`` is maintained by the ORM, so the retention windows can
        only be exercised by rewriting the column directly.
        """
        self.env.cr.execute(
            SQL(
                'UPDATE %s SET create_date = %s WHERE id IN %s',
                SQL.identifier(records._table),
                fields.Datetime.subtract(fields.Datetime.now(), days=days),
                tuple(records.ids),
            ),
        )
        records.invalidate_recordset(['create_date'])

    def _make_log(self, tool_name: str) -> models.BaseModel:
        """Create one audit-log row identified by its tool name."""
        return self.log_model.create(
            {
                'method': 'tools/call',
                'tool_name': tool_name,
                'user_id': self.env.uid,
                'status': 'ok',
            },
        )

    def _make_session(self, hours: int | None) -> models.BaseModel:
        """Create a session whose ``last_activity`` lies ``hours`` in the past.

        :param hours: ``None`` leaves ``last_activity`` unset (NULL).
        """
        last_activity = False
        if hours is not None:
            last_activity = fields.Datetime.subtract(
                fields.Datetime.now(),
                hours=hours,
            )
        return self.session_model.create(
            {
                'user_id': self.env.uid,
                'last_activity': last_activity,
            },
        )

    def _make_notification(
        self,
        session: models.BaseModel,
        delivered: bool,
    ) -> models.BaseModel:
        """Queue one notification on ``session`` with the given delivery flag."""
        return self.notification_model.create(
            {
                'session_id': session.id,
                'event_id': str(uuid.uuid4()),
                'method': 'notifications/tools/list_changed',
                'delivered': delivered,
            },
        )

    @contextmanager
    def _captured_commit(self) -> Iterator[MagicMock]:
        """Neutralise ``cr.commit`` and expose the recorded calls.

        The batched autovacuums commit once per slice so that a cron hitting
        ``limit_time_real`` keeps the batches it already deleted. ``TestCase``
        replaces ``cr.commit`` with a guard that raises, so the call has to be
        patched out here rather than removed from the model.
        """
        with patch.object(self.env.cr, 'commit') as commit:
            yield commit

    # ----------------------------------------------------------
    # Tests
    # ----------------------------------------------------------

    def test_autovacuum_logs_collects_only_expired_rows(self):
        self.config.set_param('muk_mcp.log_autovacuum_days', '30')
        stale = self._make_log('mcp_gc_stale')
        fresh = self._make_log('mcp_gc_fresh')
        self._backdate(stale, days=40)
        with self._captured_commit():
            self.log_model._autovacuum_logs()
        self.assertFalse(stale.exists())
        self.assertTrue(fresh.exists())

    def test_autovacuum_logs_honours_the_retention_parameter(self):
        self.config.set_param('muk_mcp.log_autovacuum_days', '90')
        record = self._make_log('mcp_gc_within_longer_window')
        self._backdate(record, days=40)
        with self._captured_commit():
            self.log_model._autovacuum_logs()
        self.assertTrue(record.exists())

    def test_autovacuum_logs_commits_every_batch(self):
        self.config.set_param('muk_mcp.log_autovacuum_days', '30')
        self._backdate(self._make_log('mcp_gc_committed'), days=40)
        with self._captured_commit() as commit:
            self.log_model._autovacuum_logs()
        self.assertEqual(commit.call_count, 1)

    def test_autovacuum_sessions_collects_only_idle_sessions(self):
        self.config.set_param('muk_mcp.session_timeout_hours', '24')
        idle = self._make_session(hours=48)
        recent = self._make_session(hours=1)
        self.session_model._autovacuum_sessions()
        self.assertFalse(idle.exists())
        self.assertTrue(recent.exists())

    def test_autovacuum_sessions_never_collects_null_last_activity(self):
        self.config.set_param('muk_mcp.session_timeout_hours', '24')
        orphan = self._make_session(hours=None)
        self.assertFalse(orphan.last_activity)
        self.session_model._autovacuum_sessions()
        self.assertTrue(orphan.exists())

    def test_autovacuum_notifications_respects_both_windows(self):
        session = self._make_session(hours=1)
        old_delivered = self._make_notification(session, delivered=True)
        new_delivered = self._make_notification(session, delivered=True)
        old_pending = self._make_notification(session, delivered=False)
        new_pending = self._make_notification(session, delivered=False)
        self._backdate(old_delivered, days=2)
        self._backdate(old_pending, days=10)
        self._backdate(new_pending, days=2)
        with self._captured_commit():
            self.notification_model._autovacuum_notifications()
        self.assertFalse(old_delivered.exists())
        self.assertFalse(old_pending.exists())
        self.assertTrue(new_delivered.exists())
        self.assertTrue(new_pending.exists())

    def test_autovacuum_notifications_commits_every_batch(self):
        session = self._make_session(hours=1)
        self._backdate(self._make_notification(session, delivered=True), days=2)
        with self._captured_commit() as commit:
            self.notification_model._autovacuum_notifications()
        self.assertEqual(commit.call_count, 1)
