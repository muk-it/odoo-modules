from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from unittest.mock import MagicMock, patch

from odoo import fields, models
from odoo.exceptions import UserError

from odoo.addons.muk_ai_browser.tests.common import (
    BROWSER_TOOL_NAMES,
    BrowserTestCommon,
)


class TestBridge(BrowserTestCommon):
    """Verify the AI-session bridge mirrors events onto the extension queues."""

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    @contextmanager
    def _captured_commit(self) -> Iterator[MagicMock]:
        """Neutralise ``cr.commit`` and expose the recorded calls.

        The batched autovacuum commits once per slice so that a cron hitting
        ``limit_time_real`` keeps the batches it already deleted. ``TestCase``
        replaces ``cr.commit`` with a guard that raises, so the call has to be
        patched out here rather than removed from the model.
        """
        with patch.object(self.env.cr, 'commit') as commit:
            yield commit

    def _backdate(self, records: models.BaseModel, days: int) -> None:
        """Move the creation date of ``records`` ``days`` into the past."""
        self.env.cr.execute(
            'UPDATE muk_ai_browser_event SET create_date = %s WHERE id IN %s',
            (
                fields.Datetime.subtract(fields.Datetime.now(), days=days),
                tuple(records.ids),
            ),
        )
        records.invalidate_recordset(['create_date'])

    # ----------------------------------------------------------
    # Publishing
    # ----------------------------------------------------------

    def test_published_events_are_mirrored_with_their_queue_type(self):
        ai_session = self._new_ai_session('bridge')
        browser_session = self._browser_session(ai_session=ai_session)
        ai_session._publish_event('state', {'state': 'running'})
        ai_session._publish_event('log', {'kind': 'ask_user', 'text': 'which one?'})
        ai_session._publish_event('log', {'kind': 'text', 'content': 'hi'})
        self.assertEqual(
            [entry[0] for entry in self._browser_events(browser_session)],
            ['state', 'ask', 'event'],
        )

    def test_a_mirrored_event_carries_the_original_type_and_payload(self):
        ai_session = self._new_ai_session('bridge-payload')
        browser_session = self._browser_session(ai_session=ai_session)
        ai_session._publish_event('log', {'kind': 'text', 'content': 'hello'})
        _event_type, payload = self._browser_events(browser_session)[0]
        self.assertEqual(payload['type'], 'log')
        self.assertEqual(payload['payload']['content'], 'hello')

    def test_events_are_mirrored_onto_every_attached_session(self):
        ai_session = self._new_ai_session('bridge-fanout')
        first = self._browser_session(ai_session=ai_session)
        second_key, _raw = self._device_key(label='Second Device')
        second = self._browser_session(ai_session=ai_session, key=second_key)
        ai_session._publish_event('state', {'state': 'done'})
        self.assertEqual(len(self._browser_events(first)), 1)
        self.assertEqual(len(self._browser_events(second)), 1)

    def test_an_archived_session_stops_receiving_events(self):
        ai_session = self._new_ai_session('bridge-archived')
        browser_session = self._browser_session(ai_session=ai_session)
        browser_session.active = False
        ai_session._publish_event('state', {'state': 'done'})
        self.assertEqual(self._browser_events(browser_session), [])

    # ----------------------------------------------------------
    # Origin
    # ----------------------------------------------------------

    def test_the_most_recently_active_session_supplies_the_origin(self):
        ai_session = self._new_ai_session('bridge-origin')
        older = self._browser_session(ai_session=ai_session)
        newer_key, _raw = self._device_key(label='Newer Device')
        newer = self._browser_session(ai_session=ai_session, key=newer_key)
        older.write(
            {
                'last_origin': 'https://old.example',
                'last_activity': fields.Datetime.subtract(
                    fields.Datetime.now(), hours=1
                ),
            },
        )
        newer.write(
            {
                'last_origin': 'https://new.example',
                'last_activity': fields.Datetime.now(),
            },
        )
        self.assertEqual(ai_session._browser_last_origin(), 'https://new.example')

    def test_an_unreported_origin_falls_back_to_an_empty_string(self):
        ai_session = self._new_ai_session('bridge-no-origin')
        self._browser_session(ai_session=ai_session)
        self.assertEqual(ai_session._browser_last_origin(), '')

    def test_set_origin_ignores_an_empty_report(self):
        browser_session = self._browser_session()
        browser_session._set_origin('https://kept.example')
        browser_session._set_origin(None)
        browser_session._set_origin('')
        self.assertEqual(browser_session.last_origin, 'https://kept.example')

    # ----------------------------------------------------------
    # Prompt
    # ----------------------------------------------------------

    def test_the_live_browser_note_is_absent_without_a_session(self):
        ai_session = self._new_ai_session('prompt-off')
        self.assertFalse(
            any(
                'connected to the live web browser' in note
                for note in ai_session._system_prompt_addenda()
            ),
        )

    def test_the_live_browser_note_names_the_current_origin(self):
        ai_session = self._new_ai_session('prompt-on')
        browser_session = self._browser_session(ai_session=ai_session)
        browser_session.last_origin = 'https://shop.example'
        note = next(
            entry
            for entry in ai_session._system_prompt_addenda()
            if 'connected to the live web browser' in entry
        )
        self.assertIn('https://shop.example', note)
        self.assertIn('read_page', note)

    # ----------------------------------------------------------
    # Server dispatch
    # ----------------------------------------------------------

    def test_every_browser_tool_refuses_to_run_on_the_server(self):
        tools = self.env['muk_mcp.mixin']
        for name in BROWSER_TOOL_NAMES:
            method = getattr(tools, f'_browser_{name}')
            with self.assertRaises(UserError) as capture:
                method()
            self.assertIn(name, str(capture.exception))

    # ----------------------------------------------------------
    # Retention
    # ----------------------------------------------------------

    def test_autovacuum_drops_old_events_and_keeps_recent_ones(self):
        browser_session = self._browser_session()
        events = self.env['muk_ai_browser.event']
        old_delivered = browser_session._enqueue_event('event', {'n': 1})
        fresh_delivered = browser_session._enqueue_event('event', {'n': 2})
        old_pending = browser_session._enqueue_event('event', {'n': 3})
        fresh_pending = browser_session._enqueue_event('event', {'n': 4})
        (old_delivered + fresh_delivered).write({'delivered': True})
        self._backdate(old_delivered, days=3)
        self._backdate(old_pending, days=10)
        with self._captured_commit():
            events._autovacuum_events()
        self.assertFalse(old_delivered.exists())
        self.assertFalse(old_pending.exists())
        self.assertTrue(fresh_delivered.exists())
        self.assertTrue(fresh_pending.exists())

    def test_autovacuum_keeps_a_delivered_event_inside_its_window(self):
        browser_session = self._browser_session()
        events = self.env['muk_ai_browser.event']
        delivered = browser_session._enqueue_event('event', {'n': 1})
        delivered.write({'delivered': True})
        self._backdate(delivered, days=5)
        pending = browser_session._enqueue_event('event', {'n': 2})
        self._backdate(pending, days=5)
        with self._captured_commit():
            events._autovacuum_events()
        self.assertFalse(delivered.exists(), 'delivered rows expire after a day')
        self.assertTrue(pending.exists(), 'undelivered rows survive for a week')

    def test_autovacuum_commits_every_batch(self):
        browser_session = self._browser_session()
        stale = browser_session._enqueue_event('event', {'n': 1})
        stale.write({'delivered': True})
        self._backdate(stale, days=3)
        with self._captured_commit() as commit:
            self.env['muk_ai_browser.event']._autovacuum_events()
        self.assertEqual(commit.call_count, 1)
