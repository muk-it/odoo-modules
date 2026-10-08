from __future__ import annotations

from unittest.mock import patch

from odoo import models

from odoo.addons.muk_ai.providers.openai import OpenAIProvider
from odoo.addons.muk_ai.providers.region import CUSTOM, Region
from odoo.addons.muk_ai.tests.common import AITestCommon, text_payload

RESTRICTED = Region(
    'restricted',
    'Restricted',
    'https://restricted.test/v1',
    disabled=('web_search', 'code_interpreter'),
)


class TestCapabilities(AITestCommon):
    """Verify a capability reaches the model only on a route that can serve it."""

    # ----------------------------------------------------------
    # Setup
    # ----------------------------------------------------------

    @classmethod
    def setUpClass(cls) -> None:
        """Add models with and without built-in tools."""
        super().setUpClass()
        cls.legacy, cls.gemini, cls.claude = cls.env['muk_ai.model'].create(
            [
                {
                    'name': name,
                    'provider_id': provider.id,
                    'technical_name': name,
                    'context_window': 400000,
                    'input_rate': 1.0,
                    'output_rate': 1.0,
                }
                for name, provider in (
                    ('gemini-2.5-capabilities', cls.provider_google),
                    ('gemini-3-capabilities', cls.provider_google),
                    ('claude-capabilities', cls.provider_anthropic),
                )
            ]
        )

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    def _turn(
        self, backend: str | None = None, **values
    ) -> tuple[dict, models.BaseModel]:
        """Run one turn on a new agent and return the first request and the agent."""
        self._set_params({'muk_ai.search_backend': backend})
        agent = self.env['muk_ai.agent'].create({'name': 'Capable', **values})
        session = self._session(agent_id=agent.id)
        with self._mock_responses([text_payload()]) as requests:
            session.start('go')
        return requests[0], agent

    def _assert_warning(self, agent: models.BaseModel, fragment: str) -> None:
        """Assert the agent form warns with ``fragment``, or not at all when empty."""
        if fragment:
            self.assertIn(fragment, agent.capability_warning)
        else:
            self.assertFalse(agent.capability_warning)

    # ----------------------------------------------------------
    # Tests
    # ----------------------------------------------------------

    def test_web_search_takes_the_route_the_agent_chose(self):
        legacy = {'model_id': self.legacy.id}
        hidden = {'tool_filter': ['search_read']}
        listed = {'tool_filter': ['search_read', 'web_search']}
        for backend, values, route, warning in (
            ('brave', {'web_search': 'off'}, None, ''),
            (None, {'web_search': 'auto'}, 'native', ''),
            ('brave', {'web_search': 'auto'}, 'tool', ''),
            ('brave', {'web_search': 'auto', **hidden}, 'native', ''),
            ('brave', {'web_search': 'auto', **legacy}, 'tool', ''),
            (
                None,
                {'web_search': 'auto', **legacy},
                None,
                'serves no built-in search and no Web Search Backend is set',
            ),
            ('brave', {'web_search': 'native'}, 'native', ''),
            (
                'brave',
                {'web_search': 'native', **legacy},
                None,
                'Web search is set to "Provider Built-in"',
            ),
            ('brave', {'web_search': 'tool'}, 'tool', ''),
            ('brave', {'web_search': 'tool', **listed}, 'tool', ''),
            (
                'brave',
                {'web_search': 'tool', **hidden},
                None,
                'does not list "web_search"',
            ),
            (None, {'web_search': 'tool'}, None, 'no Web Search Backend is configured'),
        ):
            with self.subTest(backend=backend, values=values):
                request, agent = self._turn(backend, **values)
                system = self._system_prompt(request)
                self.assertEqual(request['enable_web_search'], route == 'native')
                self.assertEqual('web_search' in self._tools(request), route == 'tool')
                self.assertEqual(
                    'Web search: provider built-in' in system, route == 'native'
                )
                self.assertEqual('Web search: unavailable' in system, route is None)
                self._assert_warning(agent, warning)

    def test_code_and_images_run_only_where_a_model_serves_them(self):
        code = {'enable_code_interpreter': True}
        images = {'enable_image_generation': True}
        for values, performer, drawing, warning in (
            ({}, False, False, ''),
            (code, 'Runs on OpenAI', False, ''),
            ({**code, 'model_id': self.claude.id}, 'Runs on Anthropic', False, ''),
            ({**code, 'model_id': self.gemini.id}, 'Runs on Google', False, ''),
            (
                {**code, 'model_id': self.legacy.id},
                'No provider runs code here',
                False,
                'runs no code-execution tool',
            ),
            (images, False, True, ''),
            (
                {**images, 'tool_filter': ['search_read']},
                False,
                False,
                'does not list "generate_image"',
            ),
        ):
            with self.subTest(values=values):
                request, agent = self._turn(**values)
                system = self._system_prompt(request)
                running = str(performer).startswith('Runs on')
                self.assertEqual(agent.code_interpreter_performer, performer)
                self.assertEqual(request['enable_code_interpreter'], running)
                self.assertEqual('Code interpreter:' in system, running)
                self.assertEqual('generate_image' in self._tools(request), drawing)
                self.assertEqual('Image generation:' in system, drawing)
                self._assert_warning(agent, warning)

    def test_a_region_withholds_the_capabilities_it_disables(self):
        with patch.object(OpenAIProvider, 'regions', (RESTRICTED, CUSTOM)):
            self.provider.api_region = 'restricted'
            request, agent = self._turn(web_search='auto', enable_code_interpreter=True)
            self.assertFalse(self.provider.supports_web_search)
            self.assertFalse(self.provider.supports_code_interpreter)
            self.assertTrue(self.provider.supports_vision)
            self.assertFalse(request['enable_web_search'])
            self.assertFalse(request['enable_code_interpreter'])
            self.assertIn('Web search is enabled', agent.capability_warning)
            self.assertIn('runs no code-execution tool', agent.capability_warning)
            self.assertEqual(agent.web_search, 'auto')
            self.assertTrue(agent.enable_code_interpreter)
            self.provider.api_region = 'default'
        self.env.invalidate_all()
        self.assertTrue(self.provider.supports_web_search)
        self.assertEqual(agent.code_interpreter_performer, 'Runs on OpenAI')
        self.assertFalse(agent.capability_warning)

    def test_every_unserved_capability_is_named_once(self):
        self._clear_default_models('image')
        request, agent = self._turn(
            model_id=self.legacy.id,
            web_search='auto',
            enable_image_generation=True,
            enable_code_interpreter=True,
        )
        lines = agent.capability_warning.splitlines()
        self.assertEqual(len(lines), 3)
        self.assertTrue(lines[0].startswith('Web search is enabled'))
        self.assertTrue(lines[1].startswith('Image generation is enabled'))
        self.assertIn('no image model resolves', lines[1])
        self.assertTrue(lines[2].startswith('Code interpreter is enabled'))
        self.assertFalse(self._tools(request) & {'web_search', 'generate_image'})
        self.assertFalse(request['enable_web_search'])
        self.assertFalse(request['enable_code_interpreter'])
        self.assertNotIn('Image generation:', self._system_prompt(request))
