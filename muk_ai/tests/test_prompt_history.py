from __future__ import annotations

from odoo.addons.muk_ai.tests.common import AITestCommon


class TestAiPromptHistory(AITestCommon):
    """Verify prompt revision history tracking on prompt-bearing records."""

    # ----------------------------------------------------------
    # Setup
    # ----------------------------------------------------------

    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls.agent = cls.env['muk_ai.agent'].create(
            {
                'name': 'HistoricAgent',
                'system_prompt': 'line one\nline two',
            }
        )

    # ----------------------------------------------------------
    # Tests
    # ----------------------------------------------------------

    def test_write_snapshots_old_value_when_field_changes(self):
        self.agent.write({'system_prompt': 'line one\nline two changed'})
        self.assertEqual(self.agent.prompt_history_count, 1)
        history = self.agent.prompt_history or {}
        entries = history.get('system_prompt', [])
        self.assertEqual(entries[0]['body'], 'line one\nline two')

    def test_write_does_not_snapshot_when_value_unchanged(self):
        self.agent.write({'system_prompt': 'line one\nline two'})
        self.assertEqual(self.agent.prompt_history_count, 0)

    def test_write_does_not_snapshot_when_old_value_blank(self):
        agent = self.env['muk_ai.agent'].create({'name': 'BlankPrompt'})
        agent.write({'system_prompt': 'first content'})
        self.assertEqual(agent.prompt_history_count, 0)

    def test_metadata_excludes_body(self):
        self.agent.write({'system_prompt': 'changed'})
        meta = self.agent.prompt_history_metadata or {}
        entries = meta.get('system_prompt', [])
        self.assertEqual(len(entries), 1)
        self.assertNotIn('body', entries[0])
        self.assertIn('create_date', entries[0])
        self.assertIn('create_uid', entries[0])

    def test_get_content_returns_snapshot_body(self):
        self.agent.write({'system_prompt': 'changed'})
        body = self.agent.prompt_history_get_content('system_prompt', 0)
        self.assertEqual(body, 'line one\nline two')

    def test_unified_diff_compares_revision_to_current(self):
        self.agent.write({'system_prompt': 'completely new prompt'})
        diff = self.agent.prompt_history_unified_diff('system_prompt', 0)
        self.assertIn('-line one', diff)
        self.assertIn('+completely new prompt', diff)

    def test_restore_writes_snapshot_back_and_returns_notification(self):
        self.agent.write({'system_prompt': 'overwrite'})
        result = self.agent.prompt_history_restore('system_prompt', 0)
        self.assertEqual(self.agent.system_prompt, 'line one\nline two')
        self.assertEqual(result['type'], 'ir.actions.client')
        self.assertEqual(result['tag'], 'display_notification')

    def test_history_grows_unbounded(self):
        agent = self.env['muk_ai.agent'].create(
            {
                'name': 'Unbounded',
                'system_prompt': 'v0',
            }
        )
        for i in range(1, 6):
            agent.write({'system_prompt': 'v%d' % i})
        self.assertEqual(agent.prompt_history_count, 5)
        entries = (agent.prompt_history or {}).get('system_prompt', [])
        self.assertEqual(entries[0]['body'], 'v4')
        self.assertEqual(entries[-1]['body'], 'v0')
