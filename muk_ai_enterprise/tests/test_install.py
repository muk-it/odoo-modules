from odoo.tests.common import TransactionCase, tagged


@tagged('post_install', '-at_install', 'muk_ai_enterprise')
class TestInstall(TransactionCase):
    """Step 1 acceptance: bare install works and the two M2M fields exist
    on muk_ai.agent.
    """

    def test_module_installed(self):
        module = self.env['ir.module.module'].search([
            ('name', '=', 'muk_ai_enterprise'),
        ])
        self.assertTrue(module, "muk_ai_enterprise module record missing")
        self.assertEqual(module.state, 'installed')

    def test_ee_topic_ids_field_exists(self):
        Agent = self.env['muk_ai.agent']
        self.assertIn('ee_topic_ids', Agent._fields)
        field = Agent._fields['ee_topic_ids']
        self.assertEqual(field.type, 'many2many')
        self.assertEqual(field.comodel_name, 'ai.topic')

    def test_ee_source_ids_field_exists(self):
        Agent = self.env['muk_ai.agent']
        self.assertIn('ee_source_ids', Agent._fields)
        field = Agent._fields['ee_source_ids']
        self.assertEqual(field.type, 'many2many')
        self.assertEqual(field.comodel_name, 'ai.agent.source')

    def test_agent_can_persist_ee_settings(self):
        topic = self.env['ai.topic'].create({'name': 'Bridge Smoke Topic'})
        agent = self.env['muk_ai.agent'].create({
            'name': 'Bridge Smoke Agent',
            'ee_topic_ids': [(6, 0, [topic.id])],
        })
        self.assertEqual(agent.ee_topic_ids, topic)
        agent.ee_topic_ids = [(5, 0, 0)]
        self.assertFalse(agent.ee_topic_ids)
