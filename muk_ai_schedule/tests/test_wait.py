from datetime import timedelta

from freezegun import freeze_time

from odoo import fields

from odoo.addons.muk_ai_schedule.tests.common import (
    WaitCase,
    text_payload,
    tool_payload,
)


class TestWait(WaitCase):
    """The wait tool pauses a chat, or refuses a wait it cannot keep."""

    def test_a_wait_pauses_the_round_quietly_until_its_time(self):
        with self._capture_bus() as bus:
            chat = self._waiting_chat(
                ('whoami', {}, 'c2'), note='Send the reminder', seconds=3600
            )
        pending = chat.pending_ask
        self.assertEqual(
            (chat.state, pending['kind'], pending['note'], chat.wake_count),
            ('waiting', 'wakeup', 'Send the reminder', 1),
        )
        self.assertAlmostEqual(
            chat.wake_at,
            fields.Datetime.now() + timedelta(hours=1),
            delta=timedelta(seconds=5),
        )
        self.assertEqual(chat._public_pending_ask()['resume_at'], pending['resume_at'])
        self.assertNotIn('tool_calls', chat._public_pending_ask())
        self.assertFalse(chat.awaiting_user)
        self.assertNotIn(
            'muk_ai.session_notification', [kind for _target, kind, _msg in bus]
        )
        self.assertFalse(self._outputs_for(chat, 'w1'))
        self.assertIn('wait', {tool['name'] for tool in chat._get_tool_schema()})
        self.assertIn('wait', self.env['muk_ai.agent']._rule_governed_tool_names())
        self._run_cron()
        self.assertEqual(chat.state, 'waiting')
        self._expire(chat)
        woken_at = fields.Datetime.now().replace(microsecond=0) + timedelta(minutes=1)
        with freeze_time(woken_at):
            self._run_cron()
        self.assertEqual(
            (chat.state, chat.last_text, chat.wake_at), ('done', 'done', False)
        )
        self.assertEqual(
            self._tool_output(chat, 'w1'),
            {
                'status': 'woken',
                'reason': 'time',
                'woken_at': fields.Datetime.to_string(woken_at),
                'note': 'Send the reminder',
            },
        )
        self.assertTrue(self._outputs_for(chat, 'c2'))

    def test_a_condition_that_already_holds_answers_at_once(self):
        self.partner.email = 'paid@example.com'
        chat = self._session()
        with self._mock_responses(
            [
                tool_payload(
                    ('wait', self._watch(condition=[['email', '!=', False]]), 'w1')
                ),
                text_payload('done'),
            ]
        ):
            chat.start('go')
        self.assertEqual(chat.state, 'done')
        self.assertEqual(
            self._tool_output(chat, 'w1'),
            {'status': 'condition_met', 'note': 'Check the partner'},
        )

    def test_a_wait_it_cannot_keep_is_refused_and_the_chat_goes_on(self):
        later = fields.Datetime.now().replace(microsecond=0) + timedelta(days=1)
        cases = [
            ('no time', {'note': 'x'}, 'exactly one'),
            (
                'two times',
                {'note': 'x', 'seconds': 120, 'until': '2099-01-01'},
                'exactly one',
            ),
            ('too soon', {'note': 'x', 'seconds': 10}, 'between'),
            ('too late', {'note': 'x', 'until': '2099-01-01T00:00:00'}, 'between'),
            ('bad time', {'note': 'x', 'until': 'tomorrow'}, 'ISO 8601'),
            ('no note', {'note': ' ', 'seconds': 120}, "'note'"),
            (
                'no record',
                {'note': 'x', 'seconds': 120, 'on_message': True},
                "'record_id'",
            ),
            ('no trigger', self._watch(), "'condition'"),
            (
                'unknown model',
                self._watch(model='x.nothing', on_message=True),
                'Unknown model',
            ),
            (
                'gone record',
                self._watch(record_id=0, on_message=True),
                'does not exist',
            ),
            (
                'no thread',
                self._watch(
                    model='res.country',
                    record_id=self.env.ref('base.at').id,
                    on_message=True,
                ),
                'cannot be posted',
            ),
            ('bad domain', self._watch(condition=[['nope', '=', 1]]), 'nope'),
        ]
        for name, arguments, error in cases:
            with self.subTest(name):
                chat = self._session()
                with self._mock_responses(
                    [tool_payload(('wait', arguments, 'w1')), text_payload('done')]
                ):
                    chat.start('go')
                self.assertEqual((chat.state, chat.wake_count), ('done', 0))
                self.assertIn(error, self._tool_output(chat, 'w1')['error'])
        chat = self._session()
        with self._mock_responses(
            [
                tool_payload(
                    ('wait', {'note': 'x', 'until': later.isoformat() + '+02:00'}, 'w1')
                )
            ]
        ):
            chat.start('go')
        self.assertEqual(chat.wake_at, later - timedelta(hours=2))

    def test_a_chat_waits_only_as_often_as_the_settings_allow(self):
        self.env['ir.config_parameter'].sudo().set_param('muk_ai_schedule.max_waits', 1)
        chat = self._waiting_chat(note='First', seconds=120)
        self._expire(chat)
        self._run_cron(
            tool_payload(('wait', {'note': 'Second', 'seconds': 120}, 'w2')),
            text_payload('done'),
        )
        self.assertEqual((chat.state, chat.wake_count), ('done', 1))
        self.assertIn('Finish the task', self._tool_output(chat, 'w2')['error'])

    def test_wait_runs_only_from_the_tools_array_of_a_chat(self):
        chat = self._session()
        with self._mock_responses(
            [
                tool_payload(
                    (
                        'tool_load',
                        {
                            'names': ['wait'],
                            'call': {
                                'name': 'wait',
                                'arguments': {'note': 'x', 'seconds': 120},
                            },
                        },
                        't1',
                    )
                ),
                text_payload('done'),
            ]
        ):
            chat.start('go')
        self.assertEqual(chat.state, 'done')
        self.assertIn('tools array', str(self._tool_output(chat, 't1')))
