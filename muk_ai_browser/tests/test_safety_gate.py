from odoo.addons.muk_ai_browser.tests.common import BrowserTestCommon

RISKY_ORIGIN = 'https://shop.example'


class TestSafetyGate(BrowserTestCommon):
    """Verify risky browser actions pause for approval before client dispatch."""

    def _action_requests(self, browser_session):
        return [
            payload
            for event_type, payload in self._browser_events(browser_session)
            if event_type == 'action_request'
        ]

    def _gated_session(self, origin=RISKY_ORIGIN):
        ai_session = self._new_ai_session('safety')
        browser_session = self._browser_session(ai_session=ai_session)
        browser_session.last_origin = origin
        return ai_session, browser_session

    def test_risky_click_on_ungranted_origin_enters_approval(self):
        ai_session, browser_session = self._gated_session()
        provider = self._script_provider(
            [
                self._tool_payload('click', {'element': 'Buy', 'ref': 'e1'}, 'c0'),
                self._text_payload('Done.'),
            ]
        )
        executed = []
        with provider, self._track_execute(executed):
            snapshot = ai_session.start('Click the buy button.')

        self.assertEqual(snapshot['state'], 'waiting')
        self.assertEqual(snapshot['pending_ask']['kind'], 'approval')
        self.assertNotIn('click', executed)
        self.assertEqual(self._action_requests(browser_session), [])

    def test_approve_proceeds_to_client_action(self):
        ai_session, browser_session = self._gated_session()
        provider = self._script_provider(
            [
                self._tool_payload('click', {'element': 'Buy', 'ref': 'e1'}, 'c0'),
                self._text_payload('Done.'),
            ]
        )
        executed = []
        with provider, self._track_execute(executed):
            ai_session.start('Click the buy button.')
            approved = ai_session.approve_tool()

        self.assertEqual(approved['state'], 'waiting')
        self.assertEqual(approved['pending_ask']['kind'], 'client_action')
        self.assertEqual(approved['pending_ask']['call_id'], 'c0')
        self.assertNotIn('click', executed)

        requests = self._action_requests(browser_session)
        self.assertEqual(len(requests), 1)
        self.assertEqual(requests[0]['name'], 'click')
        self.assertEqual(requests[0]['call_id'], 'c0')

        with provider:
            resumed = ai_session.submit_client_result('c0', {'ok': True})
        self.assertEqual(resumed['state'], 'done')

    def test_approve_for_session_grants_origin(self):
        ai_session, _browser_session = self._gated_session()
        provider = self._script_provider(
            [
                self._tool_payload('click', {'element': 'Buy', 'ref': 'e1'}, 'c0'),
            ]
        )
        with provider, self._track_execute([]):
            ai_session.start('Click the buy button.')
            ai_session.approve_for_session()

        self.assertEqual(
            self.env['muk_ai_browser.permission']._mode_for(
                ai_session.user_id, RISKY_ORIGIN
            ),
            'follow_plan',
        )

    def test_reject_resumes_with_rejection(self):
        ai_session, browser_session = self._gated_session()
        provider = self._script_provider(
            [
                self._tool_payload('click', {'element': 'Buy', 'ref': 'e1'}, 'c0'),
                self._text_payload('Understood, stopping.'),
            ]
        )
        with provider, self._track_execute([]):
            ai_session.start('Click the buy button.')
            rejected = ai_session.reject_tool('Not safe.')

        self.assertEqual(rejected['state'], 'done')
        self.assertEqual(self._action_requests(browser_session), [])

    def test_granted_origin_skips_gate_for_plain_click(self):
        ai_session, browser_session = self._gated_session()
        self.env['muk_ai_browser.permission']._grant(ai_session.user_id, RISKY_ORIGIN)
        provider = self._script_provider(
            [
                self._tool_payload('click', {'element': 'Open', 'ref': 'e1'}, 'c0'),
                self._text_payload('Done.'),
            ]
        )
        with provider, self._track_execute([]):
            snapshot = ai_session.start('Open the menu.')

        self.assertEqual(snapshot['pending_ask']['kind'], 'client_action')
        self.assertEqual(len(self._action_requests(browser_session)), 1)

    def test_granted_origin_still_gates_risky_keyword(self):
        ai_session, browser_session = self._gated_session()
        self.env['muk_ai_browser.permission']._grant(ai_session.user_id, RISKY_ORIGIN)
        provider = self._script_provider(
            [
                self._tool_payload(
                    'click', {'element': 'Checkout now', 'ref': 'e1'}, 'c0'
                ),
            ]
        )
        with provider, self._track_execute([]):
            snapshot = ai_session.start('Complete the purchase.')

        self.assertEqual(snapshot['pending_ask']['kind'], 'approval')
        self.assertEqual(self._action_requests(browser_session), [])

    def test_non_risky_read_page_does_not_gate(self):
        ai_session, browser_session = self._gated_session()
        provider = self._script_provider(
            [
                self._tool_payload('read_page', {'viewport_only': True}, 'c0'),
                self._text_payload('Read the page.'),
            ]
        )
        with provider, self._track_execute([]):
            snapshot = ai_session.start('Read the page.')

        self.assertEqual(snapshot['pending_ask']['kind'], 'client_action')
        self.assertEqual(len(self._action_requests(browser_session)), 1)
