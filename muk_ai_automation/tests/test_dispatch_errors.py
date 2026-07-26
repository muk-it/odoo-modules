from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from unittest.mock import patch

from odoo.tests.common import tagged

from .common import AutomationTestCommon


@tagged('post_install', '-at_install', 'muk_ai_automation')
class TestDispatchErrors(AutomationTestCommon):
    """Test that a failing agent start never rolls back the triggering write."""

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    @contextmanager
    def _failing_start(self, message: str = 'provider down') -> Iterator[None]:
        """Patch ``muk_ai.session.start`` to raise ``message``."""

        def fake(self_arg, *args, **kwargs):
            raise RuntimeError(message)

        with patch.object(
            type(self.env['muk_ai.session']),
            'start',
            autospec=True,
            side_effect=fake,
        ):
            yield

    # ----------------------------------------------------------
    # Tests
    # ----------------------------------------------------------

    def test_failing_start_marks_the_session_in_error(self):
        action = self._make_action()
        with self._failing_start():
            action.run()
        sessions = self._sessions_of(action)
        self.assertEqual(len(sessions), 1)
        self.assertEqual(sessions.state, 'error')
        self.assertIn('provider down', sessions.error_message)

    def test_failing_start_keeps_the_triggering_record_write(self):
        action = self._make_action()
        partner = self._make_partners(1, prefix='Error Partner')
        self.env.flush_all()
        self.env['base.automation'].create(
            {
                'name': 'Run AI on partner write',
                'model_id': self.partner_model.id,
                'trigger': 'on_write',
                'trigger_field_ids': [(6, 0, [self._partner_field('ref').id])],
                'action_server_ids': [(6, 0, [action.id])],
            }
        )
        with self._failing_start():
            partner.write({'ref': 'triggered'})
        partner.invalidate_recordset(['ref'])
        self.assertEqual(partner.ref, 'triggered')
        sessions = self._sessions_of(action)
        self.assertTrue(sessions)
        self.assertEqual(set(sessions.mapped('state')), {'error'})
        for message in sessions.mapped('error_message'):
            self.assertIn('provider down', message)
