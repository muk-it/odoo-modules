from odoo.tests.common import tagged

from .common import BridgeTestCommon

EE_AI_SATELLITES = [
    'ai_documents',
    'ai_livechat',
    'ai_fields',
    'ai_server_actions',
    'ai_knowledge',
    'ai_website',
    'ai_crm',
]


@tagged('post_install', '-at_install', 'muk_ai_enterprise')
class TestInstallWithSatellites(BridgeTestCommon):
    """Step 5: bridge stays clean when EE ai_* satellites are present.

    Detects which satellites are available in the registry and skips any
    that are missing so the test passes on minimal databases. When run
    against a DB that does have them, exercises the bridge against any
    topics/sources contributed by satellites.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.module = cls.env['ir.module.module']
        cls.installed_satellites = cls.module.search([
            ('name', 'in', EE_AI_SATELLITES),
            ('state', '=', 'installed'),
        ]).mapped('name')

    def test_satellite_modules_in_registry(self):
        modules = self.env['ir.module.module'].search([
            ('name', 'in', EE_AI_SATELLITES),
        ])
        if not modules:
            self.skipTest("No EE ai_* satellites available in this DB.")
        self.assertTrue(
            all(m.state in ('installed', 'uninstalled', 'uninstallable')
                for m in modules),
            "Satellites must be in a known state (no half-installed).",
        )

    def test_bridge_picks_up_satellite_topics(self):
        if not self.installed_satellites:
            self.skipTest("No EE ai_* satellites installed.")
        all_topics = self.env['ai.topic'].sudo().search([])
        if not all_topics:
            self.skipTest("No ai.topic records seeded by satellites.")
        agent = self.env['muk_ai.agent'].create({
            'name': 'Satellite Topic Borrower',
            'ee_topic_ids': [(6, 0, all_topics.ids[:5])],
        })
        self.assertTrue(agent.ee_topic_ids)
        session = self.env['muk_ai.session'].create({
            'name': 'Satellite Coexistence',
            'agent_id': agent.id,
        })
        session = session.with_context(muk_ai_session_agent_id=agent.id)
        schema = session._get_tool_schema()
        names = {t['name'] for t in schema}
        ee_names = {n for n in names if n.startswith('ee_action_')}
        if agent.ee_topic_ids.mapped('tool_ids'):
            self.assertTrue(
                ee_names,
                "Satellites contributed topics with tools but the bridge "
                "didn't expose any. Names seen: %s" % sorted(names),
            )

    def test_bridge_picks_up_satellite_sources(self):
        if not self.installed_satellites:
            self.skipTest("No EE ai_* satellites installed.")
        sources = self.env['ai.agent.source'].sudo().search([], limit=3)
        agent = self.env['muk_ai.agent'].create({
            'name': 'Satellite Source Borrower',
            'ee_source_ids': [(6, 0, sources.ids)],
        })
        self.assertEqual(agent.ee_source_ids, sources)

    def test_dangling_topic_reference_cleanup(self):
        topic = self.env['ai.topic'].create({'name': 'Disposable Topic'})
        agent = self.env['muk_ai.agent'].create({
            'name': 'Dangling Topic Agent',
            'ee_topic_ids': [(6, 0, [topic.id])],
        })
        self.assertEqual(agent.ee_topic_ids, topic)
        topic.unlink()
        agent.invalidate_recordset(['ee_topic_ids'])
        self.assertFalse(agent.ee_topic_ids)

    def test_bridge_works_without_pgvector_tables(self):
        agent = self.env['muk_ai.agent'].create({
            'name': 'No-pgvector Agent',
            'system_prompt': 'You are bare.',
        })
        session = self.env['muk_ai.session'].create({
            'name': 'No-pgvector Session',
            'agent_id': agent.id,
        })
        session.write({'conversation': [{
            'role': 'user',
            'content': [{'type': 'input_text', 'text': 'help me'}],
        }]})
        rendered = session._render_system_prompt(agent.system_prompt)
        self.assertNotIn('<rag>', rendered)
