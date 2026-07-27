from __future__ import annotations

from odoo.addons.muk_ai.tests.common import AITestCommon


class TestAutonameFromText(AITestCommon):
    """Verify automatic session naming derived from message text."""

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    def _f(self, raw: str | None) -> str:
        """Return the session name derived from the raw message text."""
        return self.env['muk_ai.session']._autoname_from_text(raw)

    # ----------------------------------------------------------
    # Tests
    # ----------------------------------------------------------

    def test_short_message_kept_as_is(self):
        self.assertEqual(self._f('Reset password'), 'Reset password')

    def test_strips_outer_quotes_and_whitespace(self):
        self.assertEqual(self._f('  "Refactor billing"  '), 'Refactor billing')

    def test_cuts_at_sentence_boundary(self):
        self.assertEqual(
            self._f('List the top 5 customers. Do you want me to filter further'),
            'List the top 5 customers',
        )

    def test_caps_at_six_words(self):
        self.assertEqual(
            self._f('one two three four five six seven eight'),
            'one two three four five six',
        )

    def test_caps_at_sixty_chars(self):
        long = 'aaaaaaaa bbbbbbbb cccccccc dddddddd eeeeeeee ffffffff gggggggg'
        self.assertLessEqual(len(self._f(long)), 60)

    def test_empty_returns_empty(self):
        self.assertEqual(self._f(''), '')
        self.assertEqual(self._f(None), '')
        self.assertEqual(self._f('   '), '')

    def test_collapses_inner_whitespace(self):
        self.assertEqual(self._f('a   b\n\nc'), 'a b c')
