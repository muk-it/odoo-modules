from __future__ import annotations

from unittest.mock import patch

from odoo import models

from odoo.addons.muk_ai.providers.openai import OpenAIProvider
from odoo.addons.muk_ai.tests.common import ImageCase


class TestCapabilityWarning(ImageCase):
    """Verify the agent form names an enabled capability that nothing serves."""

    # ----------------------------------------------------------
    # Setup
    # ----------------------------------------------------------

    def setUp(self) -> None:
        super().setUp()
        self.env['ir.config_parameter'].sudo().set_param('muk_ai.search_backend', False)
        self._clear_default_models('image')
        self.agent = self.env['muk_ai.agent'].create(
            {
                'name': 'Claude Drawer',
                'model_id': self.chat_anthropic.id,
                'enable_image_generation': True,
                'web_search': 'off',
            }
        )

    # ----------------------------------------------------------
    # Tests: image generation
    # ----------------------------------------------------------

    def test_image_generation_without_a_model_warns(self):
        self.assertTrue(self.agent.enable_image_generation)
        self.assertFalse(self.agent._resolve_model_for('image'))
        self.assertIn('Image generation is enabled', self.agent.capability_warning)
        self.assertIn('Default Image Model', self.agent.capability_warning)
        self.assertNotIn('Web search', self.agent.capability_warning)
        self.assertEqual(self.agent.image_model_placeholder, 'No image model available')

    def test_an_agent_image_model_clears_the_warning(self):
        self.agent.image_model_id = self.image
        self.assertEqual(self.agent._resolve_model_for('image'), self.image)
        self.assertFalse(self.agent.capability_warning)

    def test_a_provider_default_clears_the_warning(self):
        self.provider.default_image_model_id = self.image
        self.assertEqual(self.agent._resolve_model_for('image'), self.image)
        self.assertFalse(self.agent.capability_warning)
        self.assertEqual(
            self.agent.image_model_placeholder, 'Default: Test Image (OpenAI)'
        )

    def test_a_disabled_toggle_has_no_warning(self):
        self.agent.enable_image_generation = False
        self.assertFalse(self.agent.capability_warning)

    # ----------------------------------------------------------
    # Tests: web search
    # ----------------------------------------------------------

    def test_web_search_without_a_route_warns(self):
        self.agent.write({'enable_image_generation': False, 'model_id': False})
        with patch.object(OpenAIProvider, 'supports_web_search', False):
            self.env.invalidate_all()
            self.agent.web_search = 'auto'
            self.assertIsNone(self.agent._web_search_route())
            self.assertIn('Web search is enabled', self.agent.capability_warning)
            self.assertIn(
                'serves no built-in search',
                self.agent.capability_warning,
            )
            self.env['ir.config_parameter'].sudo().set_param(
                'muk_ai.search_backend', 'brave'
            )
            self.env.invalidate_all()
            self.assertEqual(self.agent._web_search_route(), 'tool')
            self.assertFalse(self.agent.capability_warning)

    def test_native_web_search_has_no_warning(self):
        self.agent.write({'enable_image_generation': False, 'web_search': 'auto'})
        self.assertEqual(self.agent._web_search_route(), 'native')
        self.assertFalse(self.agent.capability_warning)

    def test_both_gaps_are_listed_together(self):
        with patch.object(OpenAIProvider, 'supports_web_search', False):
            self.env.invalidate_all()
            self.agent.write({'model_id': False, 'web_search': 'auto'})
            lines = self.agent.capability_warning.splitlines()
        self.assertEqual(len(lines), 2)
        self.assertTrue(lines[0].startswith('Web search'))
        self.assertTrue(lines[1].startswith('Image generation'))

    # ----------------------------------------------------------
    # Tests: code interpreter
    # ----------------------------------------------------------

    def test_a_supported_code_interpreter_has_no_warning(self):
        self.agent.write(
            {'enable_image_generation': False, 'enable_code_interpreter': True}
        )
        self.assertEqual(self.agent._code_interpreter_route(), 'native')
        self.assertFalse(self.agent.capability_warning)

    def test_code_interpreter_without_a_provider_tool_warns(self):
        self.agent.write({'enable_image_generation': False, 'model_id': False})
        with patch.object(OpenAIProvider, 'supports_code_interpreter', False):
            self.env.invalidate_all()
            self.agent.enable_code_interpreter = True
            self.assertIsNone(self.agent._code_interpreter_route())
            warning = self.agent.capability_warning
        self.assertIn('Code interpreter is enabled', warning)
        self.assertIn('runs no code-execution tool', warning)
        self.assertIn('No setting can add one', warning)
        self.assertIn('pick a model that has one', warning)

    def test_an_unsupported_code_interpreter_keeps_its_toggle(self):
        with patch.object(OpenAIProvider, 'supports_code_interpreter', False):
            self.env.invalidate_all()
            self.agent.write({'model_id': False, 'enable_code_interpreter': True})
            self.agent.invalidate_recordset()
            self.assertTrue(self.agent.enable_code_interpreter)

    def test_web_search_and_code_interpreter_warn_together(self):
        with (
            patch.object(OpenAIProvider, 'supports_web_search', False),
            patch.object(OpenAIProvider, 'supports_code_interpreter', False),
        ):
            self.env.invalidate_all()
            self.agent.write(
                {
                    'model_id': False,
                    'enable_image_generation': False,
                    'web_search': 'auto',
                    'enable_code_interpreter': True,
                }
            )
            lines = self.agent.capability_warning.splitlines()
        self.assertEqual(len(lines), 2)
        self.assertTrue(lines[0].startswith('Web search is enabled'))
        self.assertTrue(lines[1].startswith('Code interpreter is enabled'))

    def test_every_gap_is_listed_at_once(self):
        with (
            patch.object(OpenAIProvider, 'supports_web_search', False),
            patch.object(OpenAIProvider, 'supports_code_interpreter', False),
        ):
            self.env.invalidate_all()
            self.agent.write(
                {
                    'model_id': False,
                    'web_search': 'auto',
                    'enable_code_interpreter': True,
                }
            )
            lines = self.agent.capability_warning.splitlines()
        self.assertEqual(len(lines), 3)
        self.assertTrue(lines[0].startswith('Web search is enabled'))
        self.assertTrue(lines[1].startswith('Image generation is enabled'))
        self.assertTrue(lines[2].startswith('Code interpreter is enabled'))

    # ----------------------------------------------------------
    # Tests: models that cannot run the built-in tools
    # ----------------------------------------------------------

    def _gemini_agent(self, technical_name: str, **values) -> models.BaseModel:
        """Return an agent on a Gemini model of the given generation."""
        model = (
            self.env['muk_ai.model']
            .with_context(active_test=False)
            .search(
                [
                    ('provider_id', '=', self.provider_google.id),
                    ('technical_name', '=', technical_name),
                ],
                limit=1,
            )
        )
        if not model:
            model = self.env['muk_ai.model'].create(
                {
                    'name': f'Gemini {technical_name}',
                    'provider_id': self.provider_google.id,
                    'technical_name': technical_name,
                    'context_window': 400000,
                    'input_rate': 1.0,
                    'output_rate': 1.0,
                }
            )
        model.active = True
        return self.env['muk_ai.agent'].create(
            {'name': f'Agent {technical_name}', 'model_id': model.id, **values}
        )

    def test_a_model_that_runs_builtin_tools_routes_natively(self):
        agent = self._gemini_agent(
            'gemini-3.8-flash',
            web_search='auto',
            enable_code_interpreter=True,
        )
        self.assertEqual(agent._web_search_route(), 'native')
        self.assertEqual(agent._code_interpreter_route(), 'native')
        self.assertFalse(agent.capability_warning)

    def test_a_model_that_cannot_run_builtin_search_warns_instead_of_routing(self):
        agent = self._gemini_agent('gemini-2.5-flash', web_search='auto')
        self.assertTrue(self.provider_google.supports_web_search)
        self.assertIsNone(agent._web_search_route())
        self.assertIn(
            'serves no built-in search',
            agent.capability_warning,
        )

    def test_a_backend_serves_the_model_that_cannot_run_builtin_search(self):
        agent = self._gemini_agent('gemini-2.5-flash', web_search='auto')
        self.env['ir.config_parameter'].sudo().set_param(
            'muk_ai.search_backend', 'brave'
        )
        self.env.invalidate_all()
        self.assertEqual(agent._web_search_route(), 'tool')
        self.assertFalse(agent.capability_warning)

    def test_a_model_that_cannot_run_code_execution_warns_instead_of_routing(self):
        agent = self._gemini_agent('gemini-2.5-flash', enable_code_interpreter=True)
        self.assertTrue(self.provider_google.supports_code_interpreter)
        self.assertIsNone(agent._code_interpreter_route())
        self.assertIn(
            'the model picked here runs no code-execution tool',
            agent.capability_warning,
        )

    # ----------------------------------------------------------
    # Tests: archived models
    # ----------------------------------------------------------

    def test_an_archived_provider_default_stops_resolving(self):
        self.provider.default_image_model_id = self.image
        self.assertEqual(self.agent._resolve_model_for('image'), self.image)
        self.image.active = False
        self.env.invalidate_all()
        self.assertFalse(self.provider._default_model('image'))
        self.assertFalse(self.env['muk_ai.model']._default_for('image'))
        self.assertFalse(self.agent._resolve_model_for('image'))
        self.assertEqual(self.agent.image_model_placeholder, 'No image model available')
        self.assertIn('Image generation is enabled', self.agent.capability_warning)

    def test_an_archived_provider_default_yields_to_the_next_provider(self):
        other = self.env['muk_ai.model'].create(
            {
                'name': 'Claude Image',
                'provider_id': self.provider_anthropic.id,
                'technical_name': 'claude-image-test',
                'modality': 'image',
                'input_rate': 0.0,
                'output_rate': 0.5,
            }
        )
        self.provider.default_image_model_id = self.image
        self.provider_anthropic.default_image_model_id = other
        self.assertEqual(self.env['muk_ai.model']._default_for('image'), self.image)
        self.image.active = False
        self.env.invalidate_all()
        self.assertEqual(self.env['muk_ai.model']._default_for('image'), other)

    def test_an_archived_agent_pick_falls_back_and_warns(self):
        fallback = self.env['muk_ai.model'].create(
            {
                'name': 'Fallback Image',
                'provider_id': self.provider.id,
                'technical_name': 'gpt-image-fallback',
                'modality': 'image',
                'input_rate': 0.0,
                'output_rate': 0.25,
            }
        )
        self.provider.default_image_model_id = fallback
        self.agent.image_model_id = self.image
        self.assertEqual(self.agent._resolve_model_for('image'), self.image)
        self.image.active = False
        self.env.invalidate_all()
        self.assertEqual(self.agent._resolve_model_for('image'), fallback)
        warning = self.agent.capability_warning
        self.assertIn('Image Model Test Image (OpenAI) is archived', warning)
        self.assertIn('falls back to the default model', warning)
        self.assertNotIn('Image generation is enabled', warning)

    def test_an_archived_chat_pick_falls_back_and_warns(self):
        self.agent.enable_image_generation = False
        self.assertEqual(self.agent._resolve_model_for('chat'), self.chat_anthropic)
        self.chat_anthropic.active = False
        self.env.invalidate_all()
        self.assertEqual(
            self.agent._resolve_model_for('chat'),
            self.provider_anthropic.default_chat_model_id,
        )
        warning = self.agent.capability_warning
        self.assertIn('Model Claude (Anthropic) is archived', warning)
        self.assertIn('or restore Claude (Anthropic).', warning)

    def test_an_archived_image_pick_stays_quiet_while_the_toggle_is_off(self):
        self.agent.write(
            {'enable_image_generation': False, 'image_model_id': self.image.id}
        )
        self.image.active = False
        self.env.invalidate_all()
        self.assertFalse(self.agent.capability_warning)

    # ----------------------------------------------------------
    # Tests: performer
    # ----------------------------------------------------------

    def test_a_disabled_code_interpreter_names_no_performer(self):
        self.assertFalse(self.agent.enable_code_interpreter)
        self.assertFalse(self.agent.code_interpreter_performer)

    def test_a_served_code_interpreter_names_its_vendor(self):
        self.agent.enable_code_interpreter = True
        self.assertEqual(self.agent._code_interpreter_route(), 'native')
        self.assertEqual(self.agent.code_interpreter_performer, 'Runs on Anthropic')

    def test_an_unserved_code_interpreter_names_nobody(self):
        with patch.object(OpenAIProvider, 'supports_code_interpreter', False):
            self.env.invalidate_all()
            self.agent.write({'model_id': False, 'enable_code_interpreter': True})
            self.assertIsNone(self.agent._code_interpreter_route())
            self.assertEqual(
                self.agent.code_interpreter_performer, 'No provider runs code here'
            )

    # ----------------------------------------------------------
    # Tests: placeholders
    # ----------------------------------------------------------

    def test_model_placeholder_names_the_default_chat_model(self):
        default = self.provider.default_chat_model_id
        self.assertTrue(default)
        self.agent.model_id = False
        self.assertEqual(
            self.agent.model_placeholder, f'Default: {default.display_name}'
        )
        self._clear_default_models('chat')
        self.env.invalidate_all()
        self.assertEqual(self.agent.model_placeholder, 'No chat model available')
