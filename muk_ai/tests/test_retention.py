from __future__ import annotations

from datetime import timedelta
from unittest.mock import patch

from odoo import models
from odoo.exceptions import ValidationError

from odoo.addons.muk_ai.models import session_worker
from odoo.addons.muk_ai.tests.common import AITestCommon


class TestRetention(AITestCommon):
    """Verify which finished chats the scheduled cleanup deletes."""

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    def _keep(self, session: models.BaseModel, spec: tuple, filed: bool) -> None:
        """Create a space with a retention of its own, holding ``session`` if filed.

        :param spec: ``(kind, mode, days)``; a ``personal`` space files the chat
            by hand, a ``system`` space collects it through a domain naming it
        """
        kind, mode, days = spec
        values = {'name': session.name, 'retention_mode': mode, 'retention_days': days}
        if kind == 'system':
            target = session.name if filed else 'nobody'
            values |= {'user_id': False, 'domain': repr([('name', '=', target)])}
        space = self.env['muk_ai.space'].create(values)
        if kind == 'personal' and filed:
            session.space_id = space

    # ----------------------------------------------------------
    # Tests
    # ----------------------------------------------------------

    def test_the_cleanup_deletes_only_what_nobody_keeps(self):
        patient, hasty = ('personal', 'days', 365), ('personal', 'days', 7)
        kept, default = ('personal', 'forever', 0), ('personal', 'default', 0)
        sweeps, keeps = ('system', 'days', 7), ('system', 'forever', 0)
        rows = (
            ('setting off', None, (), False, 900, 'done', False),
            ('past the setting', 30, (), False, 90, 'done', True),
            ('within the setting', 30, (), False, 10, 'done', False),
            ('ended in an error', 30, (), False, 90, 'error', True),
            ('still running', 30, (), False, 900, 'running', False),
            ('waiting for an answer', 30, (), False, 900, 'waiting', False),
            ('space keeps longer', 30, (patient,), True, 90, 'done', False),
            ('space sweeps sooner', 365, (hasty,), True, 30, 'done', True),
            ('space sweeps, setting off', None, (hasty,), True, 30, 'done', True),
            ('space on the default', 30, (default,), True, 90, 'done', True),
            ('space keeps forever', 30, (kept,), True, 900, 'done', False),
            ('loose beside a patient space', 30, (patient,), False, 90, 'done', True),
            ('system space keeps forever', 30, (keeps,), True, 900, 'done', False),
            ('system space sweeps sooner', 365, (sweeps,), True, 30, 'done', True),
            ('outside a sweeping space', 365, (sweeps,), False, 30, 'done', False),
            ('forever wins', 30, (keeps, sweeps), True, 900, 'done', False),
        )
        for index, (label, days, specs, filed, age, state, deleted) in enumerate(rows):
            with self.subTest(label):
                session = self._session(name=f'Retention {index}', state=state)
                for spec in specs:
                    self._keep(session, spec, filed)
                self._backdate(session, timedelta(days=age))
                self._set_params(
                    {
                        'muk_ai.session_retention_enabled': days is not None,
                        'muk_ai.session_retention_days': days or 30,
                    }
                )
                self.env['muk_ai.session']._gc_sessions()
                self.assertEqual(not session.exists(), deleted)

    def test_a_sweep_reports_what_it_still_owes(self):
        names = [f'Batch {index}' for index in range(3)]
        sessions = self.env['muk_ai.session'].create(
            [{'name': name, 'state': 'done'} for name in names]
        )
        self._backdate(sessions, timedelta(days=5))
        self.env['muk_ai.space'].create(
            {
                'name': 'Batch',
                'user_id': False,
                'domain': repr([('name', 'in', names)]),
                'retention_mode': 'days',
                'retention_days': 1,
            }
        )
        self._set_params({'muk_ai.session_retention_enabled': False})
        with patch.object(session_worker, 'GC_SESSION_BATCH', 2):
            self.assertEqual(self.env['muk_ai.session']._gc_sessions(), (2, 1))
            self.assertEqual(self.env['muk_ai.session']._gc_sessions(), (1, 0))
        self.assertFalse(sessions.exists())

    def test_a_space_keeping_chats_for_a_while_says_how_long(self):
        for mode, days, refused in (
            ('days', 0, True),
            ('days', -3, True),
            ('days', 7, False),
            ('forever', 0, False),
        ):
            with self.subTest(mode=mode, days=days):
                values = {
                    'name': 'Kept',
                    'retention_mode': mode,
                    'retention_days': days,
                }
                if refused:
                    with self.assertRaises(ValidationError):
                        self.env['muk_ai.space'].create(values)
                else:
                    space = self.env['muk_ai.space'].create(values)
                    self.assertEqual(space.retention_mode, mode)
