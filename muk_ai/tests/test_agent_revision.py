from .common import AITestCommon


class TestAiAgentRevision(AITestCommon):

    # ----------------------------------------------------------
    # Setup
    # ----------------------------------------------------------

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.agent = cls.env['muk_ai.agent'].create({
            'name': 'RevAgent',
            'system_prompt': 'line one\nline two',
        })
        cls.revision = cls.env['muk_ai.agent.revision'].create({
            'agent_id': cls.agent.id,
            'body': 'line one\nOLD line two',
        })

    # ----------------------------------------------------------
    # Tests
    # ----------------------------------------------------------

    def test_action_restore_copies_body_back_to_agent(self):
        result = self.revision.action_restore()
        self.assertEqual(self.agent.system_prompt, 'line one\nOLD line two')
        self.assertEqual(result['type'], 'ir.actions.client')
        self.assertEqual(result['tag'], 'display_notification')
        self.assertEqual(result['params']['type'], 'success')

    def test_action_compare_returns_dialog_with_unified_diff(self):
        result = self.revision.action_compare()
        self.assertEqual(result['type'], 'ir.actions.client')
        self.assertEqual(result['tag'], 'muk_ai.revision_dialog')
        diff = result['params']['diff']
        self.assertIn('line two', diff)
        self.assertIn('OLD line two', diff)

    def test_unified_diff_uses_agent_current_prompt(self):
        self.agent.system_prompt = 'completely new prompt'
        diff = self.revision._unified_diff()
        self.assertIn('-line one', diff)
        self.assertIn('+completely new prompt', diff)

    def test_preview_truncates_long_body(self):
        long_body = 'x' * 200
        revision = self.env['muk_ai.agent.revision'].create({
            'agent_id': self.agent.id, 'body': long_body,
        })
        self.assertTrue(revision.preview.endswith('…'))
        self.assertEqual(len(revision.preview), 121)

    def test_preview_keeps_short_body_as_is(self):
        revision = self.env['muk_ai.agent.revision'].create({
            'agent_id': self.agent.id, 'body': 'short\nhere',
        })
        self.assertEqual(revision.preview, 'short here')
        self.assertFalse(revision.preview.endswith('…'))

    def test_display_name_references_create_date(self):
        self.assertTrue(self.revision.display_name)
        self.assertIn(str(self.revision.create_date.year), self.revision.display_name)
