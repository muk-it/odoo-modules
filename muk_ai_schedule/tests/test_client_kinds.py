from __future__ import annotations

from odoo.tests.common import tagged

from .common import ScheduleTestCommon


@tagged('post_install', '-at_install', 'muk_ai_schedule')
class TestScheduleClientKinds(ScheduleTestCommon):
    """Verify schedule-spawned sessions drop the webclient client kind."""

    def test_interactive_session_keeps_webclient_kind(self):
        session = self._make_session()
        self.assertIn('webclient', session._available_client_kinds())
        names = {entry['name'] for entry in session._get_filtered_catalog()}
        self.assertIn('adjust_search', names)

    def test_scheduled_session_drops_webclient_kind(self):
        schedule = self._make_schedule(name='Kinds Schedule')
        session = self._make_session(schedule_id=schedule.id)
        self.assertNotIn('webclient', session._available_client_kinds())
        names = {entry['name'] for entry in session._get_filtered_catalog()}
        self.assertNotIn('adjust_search', names)
        self.assertFalse(session._is_client_tool('adjust_search'))
