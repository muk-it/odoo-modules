from odoo.addons.muk_ai_browser.tests.common import BrowserTestCommon


class TestVisibility(BrowserTestCommon):
    """Verify the browser tools and prompt appear only while a browser is attached."""

    def test_the_browser_is_offered_only_while_it_polls(self):
        for label, prepare, offered in (
            ('attached', lambda chat: None, True),
            ('gone quiet', self._stale, False),
            (
                'moved to another chat',
                lambda chat: self._session()._browser_attach(chat.browser_key_id),
                False,
            ),
            (
                'key revoked',
                lambda chat: setattr(chat.browser_key_id, 'active', False),
                False,
            ),
        ):
            with self.subTest(label):
                chat = self._browser_chat()
                prepare(chat)
                with self._mock_responses([self._make_text_response('done')]) as mock:
                    chat.start('hi')
                request = self._requests(mock)[0]
                self.assertEqual(
                    {'browser_click', 'browser_propose_plan'} & self._tools(request),
                    {'browser_click', 'browser_propose_plan'} if offered else set(),
                )
                self.assertEqual(
                    'https://shop.example.com' in self._system_prompt(request),
                    offered,
                )
