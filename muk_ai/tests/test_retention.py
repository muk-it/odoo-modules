from __future__ import annotations

from datetime import timedelta
from unittest.mock import patch

from odoo import fields, models
from odoo.exceptions import ValidationError
from odoo.tests.common import tagged

from odoo.addons.muk_ai.models import session as session_module
from odoo.addons.muk_ai.tests.common import AITestCommon


@tagged('post_install', '-at_install', 'muk_ai')
class TestRetention(AITestCommon):
    """Verify which finished chats the scheduled cleanup deletes."""

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    def _aged_session(self, name: str, days: int, **values) -> models.Model:
        """Create a chat that was last written to ``days`` ago.

        ``write_date`` is maintained by the ORM, so it is forced with SQL:
        writing to the record would stamp it with the current time again.
        """
        session = self.env['muk_ai.session'].create(
            {'name': name, 'state': 'done', **values}
        )
        self.env.cr.execute(
            'UPDATE muk_ai_session SET write_date = %s WHERE id = %s',
            (fields.Datetime.now() - timedelta(days=days), session.id),
        )
        session.invalidate_recordset(['write_date'])
        return session

    def _set_retention(self, days: int, enabled: bool = True) -> None:
        """Point the general setting at ``days``, switching it on or off."""
        params = self.env['ir.config_parameter'].sudo()
        params.set_param('muk_ai.session_retention_enabled', (enabled and '1') or '')
        params.set_param('muk_ai.session_retention_days', str(days))

    # ----------------------------------------------------------
    # Tests
    # ----------------------------------------------------------

    def test_nothing_is_deleted_while_the_setting_is_off(self):
        session = self._aged_session('Ancient', 900)
        self._set_retention(30, enabled=False)
        self.env['muk_ai.session']._gc_sessions()
        self.assertTrue(session.exists())

    def test_a_finished_chat_past_its_time_is_deleted(self):
        session = self._aged_session('Ancient', 90)
        self._set_retention(30)
        self.env['muk_ai.session']._gc_sessions()
        self.assertFalse(session.exists())

    def test_a_finished_chat_within_its_time_is_kept(self):
        session = self._aged_session('Recent', 10)
        self._set_retention(30)
        self.env['muk_ai.session']._gc_sessions()
        self.assertTrue(session.exists())

    def test_a_chat_still_running_is_never_deleted(self):
        session = self._aged_session('Hung', 900, state='running')
        self._set_retention(30)
        self.env['muk_ai.session']._gc_sessions()
        self.assertTrue(session.exists())

    def test_a_chat_waiting_for_an_answer_is_never_deleted(self):
        session = self._aged_session('Waiting', 900, state='waiting')
        self._set_retention(30)
        self.env['muk_ai.session']._gc_sessions()
        self.assertTrue(session.exists())

    def test_a_space_may_keep_its_chats_longer_than_the_setting(self):
        space = self.env['muk_ai.space'].create(
            {'name': 'Kept', 'retention_mode': 'days', 'retention_days': 365}
        )
        session = self._aged_session('In a patient space', 90, space_id=space.id)
        self._set_retention(30)
        self.env['muk_ai.session']._gc_sessions()
        self.assertTrue(session.exists())

    def test_a_space_may_keep_its_chats_shorter_than_the_setting(self):
        space = self.env['muk_ai.space'].create(
            {'name': 'Swept', 'retention_mode': 'days', 'retention_days': 7}
        )
        session = self._aged_session('In a hasty space', 30, space_id=space.id)
        self._set_retention(365)
        self.env['muk_ai.session']._gc_sessions()
        self.assertFalse(session.exists())

    def test_a_chat_in_no_space_is_swept_while_a_space_overrides(self):
        self.env['muk_ai.space'].create(
            {'name': 'Elsewhere', 'retention_mode': 'days', 'retention_days': 365}
        )
        session = self._aged_session('Filed nowhere', 90)
        self._set_retention(30)
        self.env['muk_ai.session']._gc_sessions()
        self.assertFalse(session.exists())

    def test_a_space_left_on_the_default_follows_the_general_setting(self):
        space = self.env['muk_ai.space'].create({'name': 'Ordinary'})
        session = self._aged_session('In an ordinary space', 90, space_id=space.id)
        self._set_retention(30)
        self.env['muk_ai.session']._gc_sessions()
        self.assertFalse(session.exists())

    def test_a_system_space_keeps_the_chats_its_domain_collects(self):
        self.env['muk_ai.space'].create(
            {
                'name': 'Linked',
                'user_id': False,
                'domain': "[('name', 'like', 'Collected')]",
                'retention_mode': 'forever',
            }
        )
        collected = self._aged_session('Collected chat', 900)
        loose = self._aged_session('Loose chat', 900)
        self._set_retention(30)
        self.env['muk_ai.session']._gc_sessions()
        self.assertTrue(collected.exists())
        self.assertFalse(loose.exists())

    def test_a_system_space_may_sweep_harder_than_the_setting(self):
        self.env['muk_ai.space'].create(
            {
                'name': 'Noisy',
                'user_id': False,
                'domain': "[('name', 'like', 'Collected')]",
                'retention_mode': 'days',
                'retention_days': 7,
            }
        )
        collected = self._aged_session('Collected chat', 30)
        loose = self._aged_session('Loose chat', 30)
        self._set_retention(365)
        self.env['muk_ai.session']._gc_sessions()
        self.assertFalse(collected.exists())
        self.assertTrue(loose.exists())

    def test_a_space_may_keep_its_chats_forever(self):
        space = self.env['muk_ai.space'].create(
            {'name': 'Forever', 'retention_mode': 'forever'}
        )
        session = self._aged_session('Kept for good', 900, space_id=space.id)
        self._set_retention(30)
        self.env['muk_ai.session']._gc_sessions()
        self.assertTrue(session.exists())

    def test_a_sweep_says_what_it_still_owes(self):
        names = ['GC batch %s' % index for index in range(3)]
        for name in names:
            self._aged_session(name, 5)
        mine = [('name', 'in', names)]
        Session = self.env['muk_ai.session']
        with patch.object(session_module, 'GC_SESSION_BATCH', 2):
            self.assertEqual(Session._gc_sessions_older_than(1, mine), (2, 1))
            self.assertEqual(Session._gc_sessions_older_than(1, mine), (1, 0))

    def test_a_space_keeping_its_chats_for_a_while_must_say_how_long(self):
        with self.assertRaises(ValidationError):
            self.env['muk_ai.space'].create({'name': 'Vague', 'retention_mode': 'days'})

    def test_a_space_keeping_forever_outranks_a_space_that_sweeps(self):
        for name, mode, days in [('Forever', 'forever', 0), ('Hasty', 'days', 7)]:
            self.env['muk_ai.space'].create(
                {
                    'name': name,
                    'user_id': False,
                    'domain': "[('name', 'like', 'Collected')]",
                    'retention_mode': mode,
                    'retention_days': days,
                }
            )
        collected = self._aged_session('Collected chat', 900)
        self._set_retention(30)
        self.env['muk_ai.session']._gc_sessions()
        self.assertTrue(collected.exists())
