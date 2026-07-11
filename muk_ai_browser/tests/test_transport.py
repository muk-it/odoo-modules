from odoo.addons.muk_ai_browser.tests.common import BrowserTestCommon


class TestTransport(BrowserTestCommon):
    """Verify browser-event sequencing, claiming and delivery marking."""

    def test_enqueue_event_increments_sequence(self):
        session = self._browser_session()
        first = session._enqueue_event('event', {'n': 1})
        second = session._enqueue_event('action_request', {'n': 2})
        third = session._enqueue_event('state', {'n': 3})
        self.assertEqual([first.seq, second.seq, third.seq], [1, 2, 3])
        self.assertEqual(session.last_event_seq, 3)

    def test_claim_marks_delivered_and_resumes(self):
        session = self._browser_session()
        for index in range(3):
            session._enqueue_event('event', {'n': index})
        rows = self.env['muk_ai_browser.event']._claim(session)
        self.assertEqual([row[0] for row in rows], [1, 2, 3])
        self.assertEqual([row[2]['n'] for row in rows], [0, 1, 2])
        self.assertFalse(self.env['muk_ai_browser.event']._claim(session))
        delivered = self.env['muk_ai_browser.event'].search(
            [('browser_session_id', '=', session.id)],
        )
        self.assertTrue(all(delivered.mapped('delivered')))

    def test_claim_caps_at_fifty_and_honors_after_seq(self):
        session = self._browser_session()
        for index in range(60):
            session._enqueue_event('event', {'n': index})
        first_batch = self.env['muk_ai_browser.event']._claim(session)
        self.assertEqual(len(first_batch), 50)
        self.assertEqual(first_batch[0][0], 1)
        self.assertEqual(first_batch[-1][0], 50)
        resume = self.env['muk_ai_browser.event']._claim(session, after_seq=50)
        self.assertEqual([row[0] for row in resume], list(range(51, 61)))
