from odoo.addons.muk_ai_browser.tests.common import BrowserTestCommon


class TestRoundtrip(BrowserTestCommon):
    """Verify the full pause/action-request/result/resume round-trip."""

    def _action_request_events(self, browser_session):
        return [
            payload
            for event_type, payload in self._browser_events(browser_session)
            if event_type == 'action_request'
        ]

    def _has_result_event(self, browser_session):
        for _event_type, payload in self._browser_events(browser_session):
            inner = (payload or {}).get('payload') or {}
            if inner.get('kind') == 'client_action_result':
                return True
        return False

    def test_browser_action_round_trip(self):
        ai_session = self._new_ai_session('roundtrip')
        browser_session = self._browser_session(ai_session=ai_session)
        browser_session.last_origin = 'https://app.example'
        self.env['muk_ai_browser.permission']._grant(
            ai_session.user_id, 'https://app.example'
        )
        provider = self._script_provider(
            [
                self._tool_payload(
                    'click',
                    {'element': 'Submit button', 'ref': 'e1'},
                    'c0',
                ),
                self._text_payload('Clicked the button.'),
            ]
        )
        executed = []
        with provider, self._track_execute(executed):
            snapshot = ai_session.start('Click the submit button.')

        self.assertEqual(snapshot['state'], 'waiting')
        self.assertEqual(snapshot['pending_ask']['kind'], 'client_action')
        self.assertEqual(snapshot['pending_ask']['call_id'], 'c0')
        self.assertEqual(snapshot['pending_ask']['name'], 'click')
        self.assertNotIn('click', executed)

        requests = self._action_request_events(browser_session)
        self.assertEqual(len(requests), 1)
        self.assertEqual(requests[0]['name'], 'click')
        self.assertEqual(requests[0]['call_id'], 'c0')
        self.assertEqual(
            requests[0]['arguments'], {'element': 'Submit button', 'ref': 'e1'}
        )

        with provider:
            resumed = ai_session.submit_client_result(
                'c0',
                {'ok': True, 'snapshot': 'role "button" "Submit" [ref=e1]'},
            )

        self.assertEqual(resumed['state'], 'done')
        self.assertIsNone(resumed['pending_ask'])
        self.assertEqual(resumed['last_text'], 'Clicked the button.')
        self.assertTrue(self._has_result_event(browser_session))
