from __future__ import annotations

from odoo import models

from odoo.addons.muk_ai.tests.common import ImageCase


class TestAgentCapabilities(ImageCase):
    """Verify a live capability reaches the model as a tool and a runtime fact."""

    # ----------------------------------------------------------
    # Setup
    # ----------------------------------------------------------

    def setUp(self) -> None:
        super().setUp()
        self._clear_default_models('image')

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    def _backend(self, backend: str | None) -> None:
        """Set or clear the global web search backend."""
        self.env['ir.config_parameter'].sudo().set_param(
            'muk_ai.search_backend', backend or False
        )
        self.env.invalidate_all()

    def _agent(self, **values) -> models.BaseModel:
        """Create an agent with every capability off unless told otherwise."""
        return self.env['muk_ai.agent'].create(
            {'name': 'Capable', 'web_search': 'off', **values}
        )

    def _drawing_agent(self) -> models.BaseModel:
        """Create an agent that resolves an image model."""
        return self._agent(
            enable_image_generation=True,
            image_model_id=self.image.id,
        )

    def _runtime(self, agent: models.BaseModel) -> str:
        """Return the runtime block of a session bound to ``agent``."""
        return self._session(agent)._build_runtime_block()

    # ----------------------------------------------------------
    # Tests: essential tools
    # ----------------------------------------------------------

    def test_the_core_default_carries_the_resource_reader(self):
        defaults = self.env['muk_ai.agent']._get_default_essential_tool_names()
        self.assertIn('read_resource', defaults)

    def test_the_search_backend_route_loads_web_search_upfront(self):
        self._backend('brave')
        session = self._session(self._agent(web_search='tool'))
        self.assertEqual(session.agent_id._web_search_route(), 'tool')
        self.assertIn('web_search', session._get_essential_tool_names())

    def test_the_built_in_route_offers_no_web_search_tool(self):
        self._backend(None)
        session = self._session(self._agent(web_search='auto'))
        self.assertEqual(session.agent_id._web_search_route(), 'native')
        self.assertNotIn('web_search', session._get_essential_tool_names())

    def test_image_generation_loads_its_tool_upfront(self):
        agent = self._drawing_agent()
        self.assertTrue(agent._resolve_model_for('image'))
        self.assertIn(
            'generate_image', self._session(agent)._get_essential_tool_names()
        )

    def test_a_dormant_capability_loads_nothing(self):
        names = self._session(self._agent())._get_essential_tool_names()
        self.assertNotIn('web_search', names)
        self.assertNotIn('generate_image', names)

    # ----------------------------------------------------------
    # Tests: runtime block
    # ----------------------------------------------------------

    def test_the_built_in_route_is_stated_as_a_runtime_fact(self):
        self._backend(None)
        runtime = self._runtime(self._agent(web_search='auto'))
        self.assertIn('Web search: provider built-in', runtime)

    def test_web_search_off_is_stated_rather_than_left_silent(self):
        self.assertIn('Web search: unavailable', self._runtime(self._agent()))

    def test_the_tool_route_states_nothing_the_tool_does_not(self):
        self._backend('brave')
        self.assertNotIn('Web search:', self._runtime(self._agent(web_search='tool')))

    def test_image_generation_is_stated_as_a_runtime_fact(self):
        self.assertIn('Image generation:', self._runtime(self._drawing_agent()))

    def test_a_dormant_capability_is_not_stated(self):
        self.assertNotIn('Image generation:', self._runtime(self._agent()))
