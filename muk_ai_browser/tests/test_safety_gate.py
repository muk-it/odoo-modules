from __future__ import annotations

from odoo import models

from odoo.addons.muk_ai_browser.tests.common import BrowserTestCommon

RISKY_ORIGIN = 'https://shop.example'


class TestSafetyGate(BrowserTestCommon):
    """Verify risky browser actions pause for approval before client dispatch."""

    def _action_requests(self, browser_session: models.BaseModel) -> list:
        """Return the action requests queued for the extension."""
        return [
            payload
            for event_type, payload in self._browser_events(browser_session)
            if event_type == 'action_request'
        ]

    def _gated_session(
        self,
        origin: str = RISKY_ORIGIN,
    ) -> tuple[models.BaseModel, models.BaseModel]:
        """Return an AI session with a browser session on ``origin``."""
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

    # ----------------------------------------------------------
    # Navigation
    # ----------------------------------------------------------

    def _gate_decision(
        self,
        name: str,
        arguments: dict,
        origin: str = RISKY_ORIGIN,
    ) -> bool:
        """Return whether the gate would pause ``name`` on ``origin``."""
        ai_session, browser_session = self._gated_session(origin=origin)
        browser_session.last_origin = origin
        return ai_session._browser_should_gate(
            {'name': name, 'arguments': arguments, 'call_id': 'c0'},
        )

    def test_navigate_always_gates_even_on_a_granted_origin(self):
        ai_session, browser_session = self._gated_session()
        self.env['muk_ai_browser.permission']._grant(ai_session.user_id, RISKY_ORIGIN)
        provider = self._script_provider(
            [
                self._tool_payload(
                    'navigate', {'url': 'https://docs.example/page'}, 'c0'
                ),
            ]
        )
        with provider, self._track_execute([]):
            snapshot = ai_session.start('Open the docs.')

        self.assertEqual(snapshot['pending_ask']['kind'], 'approval')
        self.assertEqual(self._action_requests(browser_session), [])

    def test_navigate_to_an_internal_address_reaches_the_user_first(self):
        ai_session, browser_session = self._gated_session()
        self.env['muk_ai_browser.permission']._grant(ai_session.user_id, RISKY_ORIGIN)
        provider = self._script_provider(
            [
                self._tool_payload(
                    'navigate',
                    {'url': 'http://169.254.169.254/latest/meta-data/'},
                    'c0',
                ),
            ]
        )
        with provider, self._track_execute([]):
            snapshot = ai_session.start('Fetch the instance metadata.')

        pending = snapshot['pending_ask']
        self.assertEqual(pending['kind'], 'approval')
        self.assertEqual(
            pending['preview']['arguments']['url'],
            'http://169.254.169.254/latest/meta-data/',
            'the destination is shown before the tab moves',
        )
        self.assertEqual(self._action_requests(browser_session), [])

    def test_navigate_back_always_gates(self):
        self.env['muk_ai_browser.permission']._grant(self.env.user, RISKY_ORIGIN)
        self.assertTrue(self._gate_decision('navigate_back', {}))

    def test_form_submit_gates_on_a_granted_origin(self):
        self.env['muk_ai_browser.permission']._grant(self.env.user, RISKY_ORIGIN)
        self.assertTrue(
            self._gate_decision('fill', {'ref': 'e1', 'text': 'x', 'submit': True}),
        )
        self.assertFalse(
            self._gate_decision('fill', {'ref': 'e1', 'text': 'x'}),
        )

    def test_read_tools_never_gate(self):
        for name in ('read_page', 'screenshot', 'scroll', 'hover', 'wait_for'):
            self.assertFalse(
                self._gate_decision(name, {'element': 'Checkout', 'ref': 'e1'}),
                f'{name} is a read tool and must never gate',
            )

    # ----------------------------------------------------------
    # Risky keywords
    # ----------------------------------------------------------

    def test_a_risky_keyword_in_the_origin_gates(self):
        self.env['muk_ai_browser.permission']._grant(
            self.env.user, 'https://checkout.example'
        )
        self.assertTrue(
            self._gate_decision(
                'click',
                {'element': 'Next', 'ref': 'e1'},
                origin='https://checkout.example',
            ),
        )

    def test_keyword_matching_ignores_case(self):
        self.env['muk_ai_browser.permission']._grant(self.env.user, RISKY_ORIGIN)
        self.assertTrue(
            self._gate_decision('click', {'element': 'PLACE ORDER', 'ref': 'e1'}),
        )

    def test_an_empty_keyword_configuration_disables_keyword_gating(self):
        self.env['ir.config_parameter'].sudo().set_param(
            'muk_ai_browser.risky_keywords', ''
        )
        self.env['muk_ai_browser.permission']._grant(self.env.user, RISKY_ORIGIN)
        self.assertFalse(
            self._gate_decision('click', {'element': 'Checkout now', 'ref': 'e1'}),
        )
        self.assertTrue(
            self._gate_decision('navigate', {'url': 'https://x.example'}),
            'the navigate gate does not depend on the keyword list',
        )

    def test_an_unknown_origin_gates_every_mutating_tool(self):
        for name in ('click', 'fill', 'select_option', 'press_key'):
            self.assertTrue(
                self._gate_decision(name, {'ref': 'e1'}, origin='https://new.example'),
                f'{name} must gate on an origin the user never granted',
            )

    # ----------------------------------------------------------
    # Deferral
    # ----------------------------------------------------------

    def test_a_gated_call_is_deferred_while_actions_are_open(self):
        ai_session, _browser_session = self._gated_session()
        deferred = ai_session._client_action_deferred(
            {'name': 'click', 'arguments': {'element': 'Buy', 'ref': 'e1'}},
        )
        self.assertIn('approval required', deferred)
