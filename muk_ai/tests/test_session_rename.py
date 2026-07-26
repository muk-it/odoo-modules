from __future__ import annotations

from unittest.mock import patch

from odoo.addons.muk_ai.tests.common import AITestCommon


class TestSessionStartRenames(AITestCommon):
    """Verify session renaming on the first agent turn."""

    # ----------------------------------------------------------
    # Setup
    # ----------------------------------------------------------

    def setUp(self) -> None:
        super().setUp()
        self._patches = [
            patch.object(
                type(self.env['muk_ai.session']),
                '_enqueue_user_turn',
                lambda *a, **k: None,
            ),
            patch.object(
                type(self.env['muk_ai.session']),
                '_trigger_worker',
                lambda *a, **k: None,
            ),
            patch.object(
                type(self.env['muk_ai.session']),
                '_recover_if_stuck',
                lambda *a, **k: None,
            ),
            patch.object(
                type(self.env['muk_ai.session']),
                '_build_initial_inputs',
                lambda *a, **k: [],
            ),
        ]
        for p in self._patches:
            p.start()
            self.addCleanup(p.stop)

    # ----------------------------------------------------------
    # Tests
    # ----------------------------------------------------------

    def test_renames_from_first_user_message(self):
        session = self.env['muk_ai.session'].create(
            {
                'name': 'Chat 2026-05-05 13:00:00',
            }
        )
        session.start('Reset password for partner Joe')
        self.assertEqual(session.name, 'Reset password for partner Joe')

    def test_skips_when_no_user_message(self):
        session = self.env['muk_ai.session'].create({'name': 'Original'})
        session.start(None)
        self.assertEqual(session.name, 'Original')

    def test_skips_when_conversation_already_populated(self):
        session = self.env['muk_ai.session'].create({'name': 'Original'})
        session.conversation = [{'role': 'user', 'content': []}]
        session.write({'state': 'stopped'})
        session.start('Some other prompt entirely')
        self.assertEqual(session.name, 'Original')
