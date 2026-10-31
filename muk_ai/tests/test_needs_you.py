from __future__ import annotations

from unittest.mock import patch

from odoo import models
from odoo.tests import new_test_user

from odoo.addons.muk_ai.tests.common import AITestCommon, text_payload, tool_payload


class TestNeedsYou(AITestCommon):
    """Verify what waits on a user is listed in one place and decided from there."""

    # ----------------------------------------------------------
    # Setup
    # ----------------------------------------------------------

    @classmethod
    def setUpClass(cls) -> None:
        """Flag partners as sensitive and create a plain user and their partners."""
        super().setUpClass()
        cls._mark_sensitive('res.partner')
        cls.user = new_test_user(cls.env, 'needy', groups='base.group_user')
        cls.acker, cls.wuerth = cls.env['res.partner'].create(
            [{'name': 'Acker Metallbau'}, {'name': 'Wuerth'}]
        )

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    def _wait(self, call: tuple) -> models.BaseModel:
        """Start a chat of the user whose first round makes ``call`` and pauses."""
        session = (
            self.env['muk_ai.session'].with_user(self.user).create({'name': call[0]})
        )
        with self._patch_tool(), self._mock_responses([tool_payload(call)]):
            session.start('go')
        return session

    def _needs(self) -> dict:
        """Return what waits on the user, by key."""
        rows = self.env['muk_ai.session'].with_user(self.user).get_needs_you()
        return {row['key']: row for row in rows}

    # ----------------------------------------------------------
    # Tests
    # ----------------------------------------------------------

    def test_waiting_chats_are_listed_and_single_writes_decided_there(self):
        rename = {
            'model': 'res.partner',
            'ids': [self.acker.id],
            'values': {'name': 'Acker GmbH'},
        }
        both = {'model': 'res.partner', 'ids': [self.acker.id, self.wuerth.id]}
        update = self._wait(('update_records', rename, 'c1'))
        delete = self._wait(('delete_records', both, 'c1'))
        question = self._wait(('ask_user', {'question': 'Which stage?'}, 'c1'))
        others = self.env['muk_ai.session'].create(
            [
                {'name': 'Of somebody else', 'state': 'waiting'},
                {
                    'name': 'Running a client action',
                    'user_id': self.user.id,
                    'state': 'waiting',
                    'pending_ask': {'kind': 'client_action', 'actions': []},
                },
            ]
        )
        needs = self._needs()
        for session, sublabel, approve in (
            (update, f'Update {self.acker.name}', 'approve_tool'),
            (delete, 'Delete 2 records', False),
            (question, 'Which stage?', False),
        ):
            with self.subTest(session=session.name):
                row = needs[f'muk_ai.session:{session.id}']
                self.assertEqual(
                    (row['session_id'], row['sublabel'], row['approve']),
                    (session.id, sublabel, approve),
                )
        self.assertFalse(
            {f'muk_ai.session:{other.id}' for other in others} & set(needs)
        )
        space = self.env.ref('muk_ai.space_waiting').with_user(self.user)
        waiting = self.env['muk_ai.session'].with_user(self.user).search
        self.assertEqual(waiting(space._session_domain()), question | delete | update)
        row = needs[f'muk_ai.session:{update.id}']
        record = self.env[row['res_model']].with_user(self.user).browse(row['res_id'])
        with (
            self._patch_tool() as calls,
            self._mock_responses([text_payload('renamed')]),
        ):
            getattr(record, row['approve'])()
        self.assertEqual([call['name'] for call in calls], ['update_records'])
        self.assertEqual(
            self.env['muk_ai.approval']
            .search([('session_id', '=', update.id)])
            .decision,
            'approved',
        )
        self.assertNotIn(row['key'], self._needs())
        self.assertEqual(waiting(space._session_domain()), question | delete)

    def test_any_model_answering_the_hook_adds_its_rows_after_the_chats(self):
        question = self._wait(('ask_user', {'question': 'Which stage?'}, 'c1'))
        bills = {'key': 'res.partner:bills', 'label': '3 bills to review'}
        with patch.object(
            type(self.env['res.partner']),
            '_muk_ai_attention',
            create=True,
            new=lambda self: [bills],
        ):
            keys = list(self._needs())
        self.assertLess(
            keys.index(f'muk_ai.session:{question.id}'), keys.index(bills['key'])
        )
        self.assertNotIn(bills['key'], self._needs())
