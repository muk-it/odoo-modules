from __future__ import annotations

from odoo.tests.common import TransactionCase, tagged


@tagged('post_install', '-at_install', 'muk_ai_automation')
class TestAutomationClientKinds(TransactionCase):
    """Verify action-spawned sessions drop the webclient client kind."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.agent = cls.env['muk_ai.agent'].create({'name': 'Kinds Agent'})
        cls.action = cls.env['ir.actions.server'].create(
            {
                'name': 'Kinds Action',
                'state': 'ai_agent',
                'model_id': cls.env['ir.model']._get_id('res.partner'),
                'agent_id': cls.agent.id,
                'agent_prompt': 'Hello.',
                'agent_dispatch_mode': 'single',
                'agent_record_source': 'domain',
                'agent_record_domain': '[]',
            }
        )

    def test_interactive_session_keeps_webclient_kind(self):
        session = self.env['muk_ai.session'].create({'name': 'interactive'})
        self.assertIn('webclient', session._available_client_kinds())

    def test_action_spawned_session_drops_webclient_kind(self):
        session = self.env['muk_ai.session'].create(
            {'name': 'spawned', 'action_server_id': self.action.id}
        )
        self.assertNotIn('webclient', session._available_client_kinds())
        names = {entry['name'] for entry in session._get_filtered_catalog()}
        self.assertNotIn('adjust_search', names)
