from unittest.mock import patch

from odoo.addons.muk_ai.tests.common import AITestCommon


class TestAutonameFromText(AITestCommon):

    def _f(self, raw):
        return self.env['muk_ai.session']._autoname_from_text(raw)

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


class TestSessionStartRenames(AITestCommon):

    def setUp(self):
        super().setUp()
        self._patches = [
            patch.object(
                type(self.env['muk_ai.session']),
                '_enqueue_user_turn', lambda *a, **k: None,
            ),
            patch.object(
                type(self.env['muk_ai.session']),
                '_trigger_worker', lambda *a, **k: None,
            ),
            patch.object(
                type(self.env['muk_ai.session']),
                '_recover_if_stuck', lambda *a, **k: None,
            ),
            patch.object(
                type(self.env['muk_ai.session']),
                '_build_initial_inputs', lambda *a, **k: [],
            ),
        ]
        for p in self._patches:
            p.start()
            self.addCleanup(p.stop)

    def test_renames_from_first_user_message(self):
        session = self.env['muk_ai.session'].create({
            'name': 'Chat 2026-05-05 13:00:00',
        })
        session.start('Reset password for partner Joe')
        self.assertEqual(session.name, 'Reset password for partner Joe')

    def test_skips_when_no_user_message(self):
        session = self.env['muk_ai.session'].create({'name': 'Original'})
        session.start(None)
        self.assertEqual(session.name, 'Original')

    def test_skips_when_conversation_already_populated(self):
        session = self.env['muk_ai.session'].create({'name': 'Original'})
        session.conversation = [{'role': 'user', 'content': []}]
        session.write({'state': 'stopped'})
        session.start('Some other prompt entirely')
        self.assertEqual(session.name, 'Original')
