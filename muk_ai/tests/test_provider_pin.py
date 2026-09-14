from __future__ import annotations

from odoo import models

from odoo.addons.muk_ai.tests.common import ImageCase


class TestProviderPin(ImageCase):
    """Verify the agent provider pin leads every modality it can serve."""

    # ----------------------------------------------------------
    # Setup
    # ----------------------------------------------------------

    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls.chat_openai = cls._catalog_model(
            cls.provider, 'gpt-pin-chat', 'chat', name='GPT Pin'
        )
        cls.image_openai = cls._catalog_model(
            cls.provider, 'gpt-image-pin', 'image', name='GPT Image Pin'
        )
        cls.provider.write(
            {
                'default_chat_model_id': cls.chat_openai.id,
                'default_image_model_id': cls.image_openai.id,
            }
        )
        cls.provider_anthropic.default_chat_model_id = cls.chat_anthropic.id

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    @classmethod
    def _catalog_model(
        cls,
        provider: models.BaseModel,
        technical_name: str,
        modality: str,
        name: str | None = None,
    ) -> models.BaseModel:
        """Create a catalogue model of the modality on the given provider."""
        return cls.env['muk_ai.model'].create(
            {
                'name': name or technical_name,
                'provider_id': provider.id,
                'technical_name': technical_name,
                'modality': modality,
                'context_window': 200000 if modality == 'chat' else 0,
                'input_rate': 1.0,
                'output_rate': 1.0,
            }
        )

    def _agent(self, **values) -> models.BaseModel:
        """Create an agent with web search off so only the pin is under test."""
        return self.env['muk_ai.agent'].create(
            {'name': 'Pinned', 'web_search': 'off', **values}
        )

    def _keyless_provider(self) -> models.BaseModel:
        """Create a throwaway OpenAI account that carries no API key."""
        return self.env['muk_ai.provider'].create({'name': 'openai', 'code': 'nokey'})

    # ----------------------------------------------------------
    # Tests: precedence
    # ----------------------------------------------------------

    def test_an_empty_pin_resolves_exactly_as_before(self):
        agent = self._agent()
        self.assertFalse(agent.provider_id)
        self.assertEqual(agent._resolve_model_for('chat'), self.chat_openai)
        self.assertEqual(agent._resolve_provider(), self.provider)
        self.assertEqual(
            agent.model_placeholder, f'Default: {self.chat_openai.display_name}'
        )
        self.assertFalse(agent.capability_warning)

    def test_the_pin_beats_the_company_default_provider(self):
        agent = self._agent(provider_id=self.provider_anthropic.id)
        self.assertEqual(self.env.company.default_ai_provider_id, self.provider)
        self.assertEqual(agent._resolve_model_for('chat'), self.chat_anthropic)
        self.assertEqual(agent._resolve_provider(), self.provider_anthropic)

    def test_an_explicit_model_beats_the_pin(self):
        agent = self._agent(
            provider_id=self.provider_anthropic.id,
            model_id=self.chat_openai.id,
        )
        self.assertEqual(agent._resolve_model_for('chat'), self.chat_openai)
        self.assertIn('overrides the pinned provider', agent.capability_warning)

    def test_a_model_of_the_pinned_provider_raises_no_conflict(self):
        agent = self._agent(
            provider_id=self.provider_anthropic.id,
            model_id=self.chat_anthropic.id,
        )
        self.assertEqual(agent._resolve_model_for('chat'), self.chat_anthropic)
        self.assertFalse(agent.capability_warning)

    def test_the_placeholder_names_the_default_of_the_pinned_provider(self):
        agent = self._agent(provider_id=self.provider_anthropic.id)
        self.assertEqual(
            agent.model_placeholder, f'Default: {self.chat_anthropic.display_name}'
        )

    # ----------------------------------------------------------
    # Tests: modalities
    # ----------------------------------------------------------

    def test_the_pin_leads_the_image_modality_it_catalogues(self):
        image = self._catalog_model(self.provider_anthropic, 'claude-image', 'image')
        self.provider_anthropic.default_image_model_id = image.id
        agent = self._agent(
            provider_id=self.provider_anthropic.id,
            enable_image_generation=True,
        )
        self.assertEqual(agent._resolve_model_for('chat'), self.chat_anthropic)
        self.assertEqual(agent._resolve_model_for('image'), image)
        self.assertEqual(
            agent.image_model_placeholder, f'Default: {image.display_name}'
        )

    def test_a_modality_the_pin_does_not_catalogue_falls_back(self):
        agent = self._agent(
            provider_id=self.provider_anthropic.id,
            enable_image_generation=True,
        )
        self.assertFalse(self.provider_anthropic._default_model('image'))
        self.assertEqual(agent._resolve_model_for('chat'), self.chat_anthropic)
        self.assertEqual(agent._resolve_model_for('image'), self.image_openai)
        self.assertFalse(agent.capability_warning)

    def test_an_explicit_image_model_may_leave_the_pinned_provider(self):
        agent = self._agent(
            provider_id=self.provider_anthropic.id,
            enable_image_generation=True,
            image_model_id=self.image.id,
        )
        self.assertEqual(agent._resolve_model_for('image'), self.image)
        self.assertFalse(agent.capability_warning)

    # ----------------------------------------------------------
    # Tests: credentials
    # ----------------------------------------------------------

    def test_a_pin_that_cannot_authenticate_is_honoured_and_warned(self):
        keyless = self._keyless_provider()
        model = self._catalog_model(keyless, 'gpt-nokey', 'chat')
        keyless.default_chat_model_id = model.id
        agent = self._agent(provider_id=keyless.id)
        self.assertFalse(keyless._can_serve())
        self.assertEqual(agent._resolve_model_for('chat'), model)
        self.assertIn('pinned to', agent.capability_warning)
        self.assertIn('no API key configured', agent.capability_warning)

    def test_a_keyless_provider_still_only_leads_when_pinned(self):
        keyless = self._keyless_provider()
        model = self._catalog_model(keyless, 'gpt-nokey', 'chat')
        keyless.write({'default_chat_model_id': model.id, 'sequence': 1})
        agent = self._agent()
        self.assertEqual(agent._resolve_model_for('chat'), self.chat_openai)
        self.assertFalse(agent.capability_warning)

    def test_a_pin_with_no_chat_model_falls_back_to_the_walk(self):
        self.provider_anthropic.default_chat_model_id = False
        agent = self._agent(provider_id=self.provider_anthropic.id)
        self.assertEqual(agent._resolve_model_for('chat'), self.chat_openai)
        self.assertEqual(
            agent.model_placeholder, f'Default: {self.chat_openai.display_name}'
        )

    def test_an_archived_pin_default_yields_to_the_walk(self):
        agent = self._agent(provider_id=self.provider_anthropic.id)
        self.chat_anthropic.active = False
        self.env.invalidate_all()
        self.assertEqual(agent._resolve_model_for('chat'), self.chat_openai)
