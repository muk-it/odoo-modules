from __future__ import annotations

from odoo import models

from odoo.addons.muk_ai_browser.tests.common import BrowserTestCommon

SHOP = 'https://shop.example.com'


class TestGate(BrowserTestCommon):
    """Verify what the assistant may do in the browser and what asks first."""

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    def _run(
        self, chat: models.BaseModel, name: str, arguments: dict
    ) -> models.BaseModel:
        """Start ``chat`` with a model that makes one ``name`` call, then says done."""
        with self._mock_responses(
            [
                self._make_tool_response(name, arguments, 'c0'),
                self._make_text_response('done'),
            ]
        ):
            chat.start('go')
        return chat

    # ----------------------------------------------------------
    # Tests
    # ----------------------------------------------------------

    def test_each_call_runs_asks_or_is_refused_by_site_plan_and_risk(self):
        click = {'ref': 'e1', 'element': 'Add to cart'}
        for label, rule, plan, name, arguments, outcome in (
            ('reading never asks', 'ask', None, 'browser_read_page', {}, 'client'),
            ('acting asks by default', None, None, 'browser_click', click, 'ask'),
            ('an allowed site acts', 'allow', None, 'browser_click', click, 'client'),
            (
                'a blocked site refuses reads',
                'block',
                None,
                'browser_read_page',
                {},
                'deny',
            ),
            (
                'a risky target asks on an allowed site',
                'allow',
                None,
                'browser_click',
                {'ref': 'e1', 'element': 'Delete account'},
                'ask',
            ),
            (
                'submitting asks on an allowed site',
                'allow',
                None,
                'browser_type',
                {'ref': 'e1', 'element': 'Search', 'text': 'x', 'submit': True},
                'ask',
            ),
            (
                'a plan site acts without asking',
                'ask',
                [SHOP],
                'browser_click',
                click,
                'client',
            ),
            (
                'leaving the plan asks on an allowed site',
                'allow',
                ['https://other.example.com'],
                'browser_click',
                click,
                'ask',
            ),
            (
                'pressing Enter asks like a submit',
                'allow',
                None,
                'browser_press_key',
                {'key': 'Enter'},
                'ask',
            ),
            (
                'a risky word inside another word does not ask',
                'allow',
                None,
                'browser_click',
                {'ref': 'e1', 'element': 'Border color'},
                'client',
            ),
            (
                'listing tabs never asks',
                'ask',
                None,
                'browser_tabs',
                {'action': 'list'},
                'client',
            ),
            (
                'opening a tab on another site does not ask',
                'ask',
                None,
                'browser_tabs',
                {'action': 'new', 'url': 'https://other.example.com/x'},
                'client',
            ),
            (
                'navigating outside the plan does not ask',
                'ask',
                [SHOP],
                'browser_navigate',
                {'url': 'https://www.google.com/search?q=delete'},
                'client',
            ),
            (
                'opening a tab on a blocked site is refused',
                'allow',
                None,
                'browser_tabs',
                {'action': 'new', 'url': 'https://evil.example.org/x'},
                'deny',
            ),
            (
                'navigating to a blocked site is refused',
                'allow',
                None,
                'browser_navigate',
                {'url': 'https://evil.example.org/x'},
                'deny',
            ),
        ):
            with self.subTest(label):
                if rule:
                    self._rule(SHOP, rule, self.env.user)
                self._rule('*.example.org', 'block')
                chat = self._browser_chat(SHOP)
                chat.browser_plan = {'origins': plan} if plan else False
                self._run(chat, name, arguments)
                kind = (chat.pending_ask or {}).get('kind')
                if outcome == 'deny':
                    self.assertIn(
                        'blocked_site', self._tool_output(chat, 'c0')['error']
                    )
                else:
                    self.assertEqual(
                        kind, {'client': 'client_action', 'ask': 'approval'}[outcome]
                    )
                self.env['muk_ai_browser.permission'].search([]).unlink()

    def test_acting_in_the_own_odoo_does_not_ask_for_the_site(self):
        odoo = self.env['muk_ai.session']._browser_origin_of(
            self.env['muk_ai.session'].get_base_url()
        )
        for plan in (None, [SHOP]):
            with self.subTest(plan=plan):
                chat = self._browser_chat(odoo)
                chat.browser_plan = {'origins': plan} if plan else False
                self._run(chat, 'browser_click', {'ref': 'e1', 'element': 'Save'})
                self.assertEqual(chat.pending_ask['kind'], 'client_action')

    def test_allowing_a_site_for_the_session_grants_only_a_plain_ask(self):
        for element, granted in (('Add to cart', 'allow'), ('Delete account', 'ask')):
            with self.subTest(element):
                chat = self._run(
                    self._browser_chat(SHOP),
                    'browser_click',
                    {'ref': 'e1', 'element': element},
                )
                chat.approve_for_session()
                self.assertEqual(
                    [
                        (action['call_id'], action['origin'])
                        for action in chat._browser_poll()['actions']
                    ],
                    [('c0', SHOP)],
                )
                self.assertEqual(
                    self.env['muk_ai_browser.permission']._mode_for(
                        self.env.user, SHOP
                    ),
                    granted,
                )
                self.env['muk_ai_browser.permission'].search([]).unlink()

    def test_an_approved_plan_records_its_sites(self):
        plan = {
            'summary': 'Order the book',
            'steps': ['Open the book', 'Add it to the cart'],
            'origins': ['HTTPS://Shop.Example.com/books', 'https://pay.example.com'],
        }
        for origins in (['The shop page'], {'page': SHOP}):
            with self.subTest(origins=origins):
                chat = self._run(
                    self._browser_chat(SHOP),
                    'browser_propose_plan',
                    {**plan, 'origins': origins},
                )
                self.assertIn(f'["{SHOP}"]', self._tool_output(chat, 'c0')['error'])
                self.assertFalse(chat.browser_plan)
        chat = self._run(
            self._browser_chat(SHOP),
            'tool_load',
            {
                'names': ['browser_propose_plan'],
                'call': {'name': 'browser_propose_plan', 'arguments': plan},
            },
        )
        self.assertEqual(
            self._tool_output(chat, 'c0')['call']['output']['error'],
            'requires_approval',
        )
        self.assertFalse(chat.browser_plan)
        chat = self._run(self._browser_chat(SHOP), 'browser_propose_plan', plan)
        self.assertEqual(chat.pending_ask['kind'], 'approval')
        self.assertEqual(
            [row['value'] for row in chat.pending_ask['preview']['properties']],
            [
                '1. Open the book\n2. Add it to the cart',
                'shop.example.com, pay.example.com',
            ],
        )
        self.assertFalse(chat.browser_plan)
        with self._mock_responses([self._make_text_response('done')]):
            chat.approve_tool()
        self.assertEqual(
            chat.browser_plan['origins'], [SHOP, 'https://pay.example.com']
        )
        self.assertEqual(chat.state, 'done')
