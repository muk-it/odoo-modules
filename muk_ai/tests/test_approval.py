from __future__ import annotations

import json

from odoo import models
from odoo.tests import new_test_user

from odoo.addons.muk_ai.tests.common import AITestCommon, text_payload, tool_payload
from odoo.addons.muk_ai.tools.call import clean_ask_preview


class TestApproval(AITestCommon):
    """Verify risky tool calls wait for a person's decision before they run."""

    # ----------------------------------------------------------
    # Setup
    # ----------------------------------------------------------

    @classmethod
    def setUpClass(cls) -> None:
        """Flag partners as sensitive and create a partner to delete."""
        super().setUpClass()
        cls._mark_sensitive('res.partner')
        cls.approval = cls.env['muk_ai.approval']
        cls.partner = cls.env['res.partner'].create({'name': 'Doomed Partner'})

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    def _delete(self, call_id: str = 'c1') -> dict:
        """Build a provider round deleting the test partner."""
        arguments = {'model': 'res.partner', 'ids': [self.partner.id]}
        return tool_payload(('delete_records', arguments, call_id))

    def _audit(self, session: models.BaseModel) -> list[tuple]:
        """Return the audited ``(decision, reject_reason)`` pairs of a chat."""
        records = self.approval.search([('session_id', '=', session.id)], order='id')
        return [(record.decision, record.reject_reason) for record in records]

    def _signature(self, tool: str, arguments: dict) -> str:
        """Return the approval signature of a call on the test partners."""
        risk = self.approval._assess_risk(tool, {'model': 'res.partner', **arguments})
        return risk['signature']

    def _digest(self, preview: dict | None) -> dict | None:
        """Reduce a preview to what its card shows."""
        if preview is None:
            return None
        digest = {'kind': preview['kind']}
        if 'targets' in preview:
            digest['targets'] = [item['display_name'] for item in preview['targets']]
        if 'changes' in preview:
            digest['changes'] = [
                (item['field'], item['from'], item['to']) for item in preview['changes']
            ]
        if 'properties' in preview:
            digest['properties'] = [
                (item['field'], item['value'], item.get('record'))
                for item in preview['properties']
            ]
        if 'method' in preview:
            digest['method'] = preview['method']
        return digest

    # ----------------------------------------------------------
    # Tests
    # ----------------------------------------------------------

    def test_risk_follows_the_sensitive_flag_and_the_tool(self):
        for tool, arguments, reason in (
            (
                'delete_records',
                {'model': 'res.partner', 'ids': [1, '2', True]},
                'unlink 2 record(s)',
            ),
            (
                'call_method',
                {'model': 'res.partner', 'ids': [1], 'method': ' action_archive '},
                'call action_archive on 1 record(s)',
            ),
            (
                'update_records',
                {'model': 'res.partner', 'ids': [1], 'values': {'user_id': 1}},
                'update 1 record(s)',
            ),
            ('create_records', {'model': 'res.users', 'values': {}}, 'a new record'),
            ('update_records', {'model': 'res.partner.category', 'ids': [1]}, None),
            ('search_read', {'model': 'res.partner'}, None),
            ('delete_records', {'model': 'no.such.model', 'ids': [1]}, None),
        ):
            with self.subTest(tool=tool, model=arguments['model']):
                risk = self.approval._assess_risk(tool, arguments)
                if reason is None:
                    self.assertIsNone(risk)
                else:
                    self.assertIn(reason, risk['reason'])
                    self.assertEqual(
                        (risk['tool'], risk['model']), (tool, arguments['model'])
                    )

    def test_a_signature_names_the_tool_the_model_and_the_method(self):
        for first, second, same in (
            (
                ('update_records', {'ids': [1], 'values': {'name': 'A'}}),
                ('update_records', {'ids': [9], 'values': {'user_id': 3}}),
                True,
            ),
            (
                ('delete_records', {'ids': [1]}),
                ('update_records', {'ids': [1], 'values': {}}),
                False,
            ),
            (
                ('call_method', {'ids': [1], 'method': 'action_archive'}),
                ('call_method', {'ids': [1], 'method': 'action_unarchive'}),
                False,
            ),
        ):
            with self.subTest(first=first, second=second):
                self.assertEqual(
                    self._signature(*first) == self._signature(*second), same
                )

    def test_a_preview_describes_the_change_in_the_users_terms(self):
        target = self.env['res.partner'].create({'name': 'Preview Target'})
        other = self.env['res.partner'].create({'name': 'Second Target'})
        tag = self.env['res.partner.category'].create({'name': 'Preview Tag'})
        user = self.env.ref('base.user_admin')
        for tool, arguments, digest in (
            (
                'update_records',
                {'ids': [target.id], 'values': {'name': 'New Name', 'type': 'invoice'}},
                {
                    'kind': 'update',
                    'targets': ['Preview Target'],
                    'changes': [
                        ('name', 'Preview Target', 'New Name'),
                        ('type', 'Contact', 'Invoice'),
                    ],
                },
            ),
            (
                'update_records',
                {
                    'ids': [target.id, other.id],
                    'values': {
                        'name': 'Same',
                        'user_id': user.id,
                        'is_company': True,
                        'category_id': [tag.id],
                    },
                },
                {
                    'kind': 'update',
                    'targets': ['Preview Target', 'Second Target'],
                    'changes': [
                        ('name', '(varies)', 'Same'),
                        ('user_id', '', user.display_name),
                        ('is_company', '', 'Yes'),
                        ('category_id', '', 'Preview Tag'),
                    ],
                },
            ),
            (
                'update_records',
                {
                    'ids': [target.id],
                    'values': {'color': 24000, 'partner_latitude': 48.2},
                },
                {
                    'kind': 'update',
                    'targets': ['Preview Target'],
                    'changes': [
                        ('color', '0', '24,000'),
                        ('partner_latitude', '0.0000000', '48.2000000'),
                    ],
                },
            ),
            (
                'update_records',
                {
                    'ids': [target.id],
                    'values': {
                        'category_id': [[6, 0, [tag.id]]],
                        'child_ids': [
                            [0, 0, {'name': 'Child', 'is_company': True}],
                            [4, other.id],
                            [3, other.id],
                        ],
                    },
                },
                {
                    'kind': 'update',
                    'targets': ['Preview Target'],
                    'changes': [
                        ('category_id', '', 'Preview Tag'),
                        (
                            'child_ids',
                            '',
                            f'Child, Is a Company Yes\nSecond Target\n[3, {other.id}]',
                        ),
                    ],
                },
            ),
            (
                'delete_records',
                {'ids': [target.id, other.id]},
                {'kind': 'delete', 'targets': ['Preview Target', 'Second Target']},
            ),
            (
                'call_method',
                {'ids': [target.id], 'method': 'action_archive'},
                {
                    'kind': 'call',
                    'targets': ['Preview Target'],
                    'method': 'action_archive',
                },
            ),
            (
                'create_records',
                {'values': {'name': 'New Guy', 'email': 'new@example.com'}},
                {
                    'kind': 'create',
                    'properties': [
                        ('name', 'New Guy', None),
                        ('email', 'new@example.com', None),
                    ],
                },
            ),
            (
                'create_records',
                {'values': [{'name': 'One'}]},
                {'kind': 'create', 'properties': [('name', 'One', None)]},
            ),
            (
                'create_records',
                {'values': [{'name': 'One'}, {'name': 'Two'}]},
                {
                    'kind': 'create',
                    'properties': [('name', 'One', 1), ('name', 'Two', 2)],
                },
            ),
            ('create_records', {'values': ['name=X']}, None),
            (
                'delete_records',
                {'model': 'no.such.model', 'ids': [1]},
                {'kind': 'delete', 'targets': []},
            ),
            ('update_records', {'ids': [target.id], 'values': 'name=X'}, None),
            ('search_read', {'values': {'name': 'X'}}, None),
        ):
            with self.subTest(tool=tool, arguments=arguments):
                preview = self.approval._build_preview(
                    tool, {'model': 'res.partner', **arguments}
                )
                self.assertEqual(self._digest(preview), digest)

    def test_a_preview_hides_what_the_user_cannot_read(self):
        restricted = new_test_user(
            self.env, login='approval-restricted', groups='base.group_user'
        )
        secret = self.env['ir.config_parameter'].create(
            {'key': 'muk_ai.approval_probe', 'value': 'TOP-SECRET'}
        )
        preview = self.approval.with_user(restricted)._build_preview(
            'update_records',
            {
                'model': 'ir.config_parameter',
                'ids': [secret.id],
                'values': {'value': 'redacted'},
            },
        )
        self.assertNotIn('TOP-SECRET', json.dumps(preview))
        self.assertEqual(
            self._digest(preview),
            {
                'kind': 'update',
                'targets': ['(no access)'],
                'changes': [('value', '', 'redacted')],
            },
        )

    def test_a_risky_call_waits_for_the_decision(self):
        for method, args, state, output, audit in (
            ('approve_tool', (), 'done', {'success': True}, [('approved', False)]),
            (
                'approve_for_session',
                (),
                'done',
                {'success': True},
                [('approved_session', False)],
            ),
            (
                'reject_tool',
                ('not now',),
                'done',
                {'error': 'rejected_by_user', 'reason': 'not now'},
                [('rejected', 'not now')],
            ),
            (
                'action_stop',
                (),
                'stopped',
                {'status': 'cancelled', 'reason': 'stopped_by_user'},
                [],
            ),
        ):
            with self.subTest(method=method):
                session = self._session()
                with (
                    self._patch_tool({'delete_records': {'success': True}}) as calls,
                    self._mock_responses([self._delete(), text_payload('done')]),
                ):
                    snapshot = session.start('delete the partner')
                    ask = snapshot['pending_ask']
                    self.assertEqual(
                        (snapshot['state'], ask['kind'], ask['resolution']),
                        ('waiting', 'approval', 'yesno'),
                    )
                    self.assertEqual(
                        self._digest(ask['preview']),
                        {'kind': 'delete', 'targets': ['Doomed Partner']},
                    )
                    self.assertEqual(
                        self._events(session, 'ask_user')[0]['preview'],
                        ask['preview'],
                    )
                    self.assertEqual(calls, [])
                    getattr(session, method)(*args)
                self.assertEqual(session.state, state)
                self.assertFalse(session.pending_ask)
                self.assertEqual(self._tool_output(session, 'c1'), output)
                self.assertEqual(
                    [call['name'] for call in calls],
                    ['delete_records'] if method.startswith('approve') else [],
                )
                self.assertEqual(self._audit(session), audit)
                self.assertEqual(
                    [event['decision'] for event in self._events(session, 'approval')],
                    [decision for decision, _reason in audit],
                )

    def test_an_approval_for_the_session_is_remembered_there_only(self):
        heir = new_test_user(self.env, login='approval-heir', groups='base.group_user')
        for name, follow_up, remembered in (
            ('same chat', lambda chat: chat, True),
            ('another chat', lambda chat: self._session(), False),
            ('cleared chat', lambda chat: chat.clear() and chat, False),
            (
                'handed over',
                lambda chat: chat.action_handover(heir.id) and chat.with_user(heir),
                False,
            ),
        ):
            with self.subTest(name):
                session = self._session()
                with (
                    self._patch_tool() as calls,
                    self._mock_responses(
                        [
                            self._delete('c1'),
                            text_payload('first'),
                            self._delete('c2'),
                            text_payload('second'),
                        ]
                    ),
                ):
                    session.start('delete the partner')
                    session.approve_for_session()
                    chat = follow_up(session)
                    calls.clear()
                    chat.send_message('delete it again')
                self.assertEqual(chat.state, 'done' if remembered else 'waiting')
                self.assertEqual(bool(calls), remembered)
                self.assertEqual(
                    ('auto_approved', False) in self._audit(chat), remembered
                )

    def test_an_inline_tool_load_call_passes_the_same_gate(self):
        for model, mode, gated in (
            ('res.partner', None, True),
            ('res.partner.category', None, False),
            ('res.partner', 'off', False),
        ):
            with self.subTest(model=model, mode=mode):
                session = self._session()
                session.set_approval_mode(mode)
                arguments = {
                    'names': ['update_records'],
                    'call': {
                        'name': 'update_records',
                        'arguments': {
                            'model': model,
                            'ids': [self.partner.id],
                            'values': {'name': 'Owned'},
                        },
                    },
                }
                with (
                    self._patch_tool() as calls,
                    self._mock_responses(
                        [tool_payload(('tool_load', arguments, 'c1')), text_payload()]
                    ),
                ):
                    session.start('rename it')
                    self.assertEqual(
                        (session.state, len(calls)),
                        ('waiting', 0) if gated else ('done', 1),
                    )
                    if gated:
                        self.assertEqual(
                            session.pending_ask['preview']['kind'], 'update'
                        )
                        session.approve_tool()
                inline = self._tool_output(session, 'c1')['call']
                self.assertEqual((session.state, inline['ok']), ('done', True))
                self.assertEqual(json.loads(inline['output']), {'ok': True})

    def test_an_ask_user_preview_is_reduced_to_what_a_card_can_show(self):
        for preview, cleaned in (
            (None, None),
            ('update', None),
            ([{'kind': 'update'}], None),
            ({'kind': 'explode'}, None),
            ({'title': 'No kind'}, None),
            (
                {'kind': 'update', 'title': 'Update', 'extra': {'a': 1}},
                {'kind': 'update', 'title': 'Update', 'targets': [], 'changes': []},
            ),
            (
                {'kind': 'delete', 'targets': [{'id': 1}, 'junk', 7]},
                {'kind': 'delete', 'targets': [{'id': 1}]},
            ),
            (
                {'kind': 'create', 'properties': None},
                {'kind': 'create', 'properties': []},
            ),
            (
                {'kind': 'call', 'method': 'action_post'},
                {'kind': 'call', 'method': 'action_post', 'targets': []},
            ),
        ):
            with self.subTest(preview=preview):
                self.assertEqual(clean_ask_preview(preview), cleaned)
        session = self._session()
        question = {
            'question': 'Proceed?',
            'resolution': 'yesno',
            'preview': {'kind': 'update', 'model': 'res.partner', 'changes': 'all'},
        }
        with self._mock_responses([tool_payload(('ask_user', question, 'c1'))]):
            snapshot = session.start('update the partner')
        self.assertEqual(
            snapshot['pending_ask']['preview'],
            {'kind': 'update', 'model': 'res.partner', 'targets': [], 'changes': []},
        )
