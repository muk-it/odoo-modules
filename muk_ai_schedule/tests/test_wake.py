from markupsafe import Markup

from odoo.exceptions import UserError

from odoo.addons.muk_ai_schedule.tests.common import WaitCase, text_payload


class TestWake(WaitCase):
    """A waiting chat wakes when its record is ready, a message arrives or its owner says."""

    def test_the_watched_record_wakes_the_chat(self):
        paid = [['email', '=', 'paid@example.com']]
        cases = [
            (
                'ready',
                'condition_met',
                {'condition': paid},
                lambda chat, record: record.write({'email': 'paid@example.com'}),
            ),
            (
                'message',
                'message',
                {'on_message': True},
                lambda chat, record: record.message_post(
                    body='Paid', message_type='comment'
                ),
            ),
            (
                'timeout',
                'timeout',
                {'condition': paid},
                lambda chat, record: self._expire(chat),
            ),
            (
                'deleted',
                'record_deleted',
                {'on_message': True},
                lambda chat, record: record.unlink(),
            ),
            (
                'model gone',
                'record_deleted',
                {'condition': paid},
                lambda chat, record: chat.write({'wake_res_model': 'x.gone'}),
            ),
            (
                'field gone',
                'condition_invalid',
                {'condition': paid},
                lambda chat, record: chat.write(
                    {
                        'pending_ask': {
                            **chat.pending_ask,
                            'condition': [['gone', '=', 1]],
                        }
                    }
                ),
            ),
        ]
        for name, reason, arguments, change in cases:
            with self.subTest(name):
                record = self.partner.copy()
                chat = self._waiting_chat(
                    **self._watch(record_id=record.id, **arguments)
                )
                self.assertEqual(
                    (chat.state, chat.wake_res_model, chat.wake_res_id),
                    ('waiting', 'res.partner', record.id),
                )
                self._run_cron()
                self.assertEqual(chat.state, 'waiting')
                change(chat, record)
                self._run_cron()
                self.assertEqual(
                    (chat.state, self._tool_output(chat, 'w1')['reason']),
                    ('done', reason),
                )
                self.assertFalse(chat.wake_res_model)

    def test_a_message_on_the_record_reaches_the_woken_chat(self):
        chat = self._waiting_chat(**self._watch(on_message=True))
        other = self._waiting_chat(**self._watch(condition=[['email', '!=', False]]))
        self.partner.message_post(body='Logged', message_type='notification')
        self.partner.copy().message_post(body='Elsewhere', message_type='comment')
        self._run_cron()
        self.assertEqual(chat.state, 'waiting')
        self.partner.message_post(
            body=Markup('<p>It is <b>paid</b></p>'),
            message_type='comment',
            subject='Invoice',
        )
        self._run_cron()
        message = self._tool_output(chat, 'w1')['message']
        self.assertEqual(
            (message['body'], message['subject'], message['author']),
            ('It is *paid*', 'Invoice', self.env.user.partner_id.display_name),
        )
        self.assertEqual(other.state, 'waiting')

    def test_the_owner_wakes_or_stops_a_waiting_chat(self):
        chat = self._waiting_chat(note='Later', seconds=3600)
        with self._mock_responses([text_payload('woken')]):
            chat.action_wake_now()
        self.assertEqual(
            (chat.state, self._tool_output(chat, 'w1')['reason']), ('done', 'manual')
        )
        with self.assertRaises(UserError):
            chat.action_wake_now()
        with self._mock_responses([text_payload('later')]):
            chat.send_message('Thanks')
        self.assertEqual(chat.last_text, 'later')
        chat = self._waiting_chat(note='Later', seconds=3600)
        with self._mock_responses([text_payload('answered')]):
            chat.send_message('Any news?')
        self.assertEqual(
            (chat.state, chat.last_text, self._tool_output(chat, 'w1')['reason']),
            ('done', 'answered', 'user_message'),
        )
        self.assertEqual(self._events(chat, 'user_message')[-1]['content'], 'Any news?')
        chat = self._waiting_chat(note='Later', seconds=3600)
        chat.action_stop()
        self.assertEqual((chat.state, chat.wake_at), ('stopped', False))
        self.assertEqual(self._tool_output(chat, 'w1')['reason'], 'stopped_by_user')
        self._run_cron()
        self.assertEqual(chat.state, 'stopped')

    def test_a_chat_that_waits_without_a_call_takes_its_note_as_the_next_message(self):
        chat = self._session()
        with self._mock_responses([text_payload('hi')]):
            chat.start('go')
        chat.write(
            {
                'state': 'waiting',
                'pending_ask': {'kind': 'wakeup', 'note': 'Send the digest'},
            }
        )
        self._expire(chat)
        self._run_cron(text_payload('sent'))
        self.assertEqual((chat.state, chat.last_text), ('done', 'sent'))
        self.assertEqual(
            self._events(chat, 'user_message')[-1]['content'], 'Send the digest'
        )

    def test_a_wake_that_fails_or_finds_the_chat_busy_leaves_the_others_waking(self):
        failing = self._waiting_chat(note='First', seconds=120)
        busy = self._waiting_chat(note='Second', seconds=120)
        self._expire(failing | busy)
        with self._hold_lock(busy.id):
            self._run_cron(RuntimeError('boom'))
        self.assertEqual((failing.state, failing.error_message), ('error', 'boom'))
        self.assertEqual(busy.state, 'waiting')
        busy.action_stop()
        self.env['muk_ai.session']._wake_in_worker(busy.id, 'time')
        self.assertEqual(busy.state, 'stopped')
