from odoo.tests.common import TransactionCase, tagged


@tagged('post_install', '-at_install', 'muk_ai_skills', 'prompt')
class TestPromptAddendum(TransactionCase):

    # ----------------------------------------------------------
    # Setup
    # ----------------------------------------------------------

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Skill = cls.env['muk_ai.skill']
        cls.Session = cls.env['muk_ai.session']
        cls.Agent = cls.env['muk_ai.agent']
        cls.agent = cls.Agent.create({
            'name': 'Prompt Test Agent',
            'system_prompt': 'You are a helpful assistant.',
        })
        cls.other_agent = cls.Agent.create({
            'name': 'Prompt Test Agent Other',
        })

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    def _make_session(self, agent=None):
        return self.Session.create({
            'name': 'Prompt Test Session',
            'agent_id': (agent or self.agent).id,
        })

    def _make_skill(self, **vals):
        defaults = {
            'name': 'sample_skill',
            'description': 'Sample skill description.',
        }
        defaults.update(vals)
        return self.Skill.create(defaults)

    def _drop_existing_skills(self):
        self.env['muk_ai.skill'].sudo().search([]).unlink()

    # ----------------------------------------------------------
    # Tests
    # ----------------------------------------------------------

    def test_no_skills_no_addendum(self):
        self._drop_existing_skills()
        session = self._make_session()
        rendered = session._effective_system_prompt()
        self.assertNotIn('<available_skills>', rendered)

    def test_global_skill_appears_in_addendum(self):
        self._drop_existing_skills()
        self._make_skill(name='alpha', description='Do alpha things.')
        session = self._make_session()
        rendered = session._effective_system_prompt()
        self.assertIn('<available_skills>', rendered)
        self.assertIn('`alpha`', rendered)
        self.assertIn('Do alpha things.', rendered)

    def test_scoped_skill_only_for_matching_agent(self):
        self._drop_existing_skills()
        self._make_skill(
            name='only_other',
            description='Hidden from primary agent.',
            agent_ids=[(6, 0, [self.other_agent.id])],
        )
        session = self._make_session(self.agent)
        rendered = session._effective_system_prompt()
        self.assertNotIn('only_other', rendered)

    def test_addendum_appended_after_base_prompt(self):
        self._drop_existing_skills()
        self._make_skill(name='beta', description='Beta does beta.')
        session = self._make_session()
        rendered = session._effective_system_prompt()
        base = 'You are a helpful assistant.'
        self.assertIn(base, rendered)
        self.assertLess(rendered.index(base), rendered.index('<available_skills>'))

    def test_inactive_skill_omitted(self):
        self._drop_existing_skills()
        skill = self._make_skill(name='gamma', description='Gamma.')
        skill.active = False
        session = self._make_session()
        rendered = session._effective_system_prompt()
        self.assertNotIn('gamma', rendered)
