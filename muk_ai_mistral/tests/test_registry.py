from .common import MistralTestCommon
from odoo.addons.muk_ai.providers import REGISTRY
from odoo.addons.muk_ai_mistral.providers.mistral import MistralProvider


class TestMistralRegistry(MistralTestCommon):
    """Assert the Mistral provider is registered, seeded and selectable."""

    # ----------------------------------------------------------
    # Registry
    # ----------------------------------------------------------

    def test_provider_registered(self):
        self.assertIn('mistral', REGISTRY)
        self.assertIs(REGISTRY['mistral'], MistralProvider)

    def test_provider_in_selection(self):
        selection = dict(self.provider._selection_name())
        self.assertEqual(selection.get('mistral'), 'Mistral AI')

    def test_get_client_returns_mistral_provider(self):
        client = self.provider._get_client()
        self.assertIsInstance(client, MistralProvider)
        self.assertEqual(client.api_url, 'https://api.mistral.ai/v1')

    # ----------------------------------------------------------
    # Seeds
    # ----------------------------------------------------------

    def test_default_model_seeded(self):
        self.assertEqual(
            self.provider.default_chat_model_id.technical_name,
            'mistral-medium-latest',
        )

    def test_models_seeded_for_provider(self):
        models = self.env['muk_ai.model'].search(
            [
                ('provider_id', '=', self.provider.id),
                ('modality', '=', 'chat'),
            ]
        )
        self.assertEqual(
            set(models.mapped('technical_name')),
            {
                'mistral-large-latest',
                'mistral-medium-latest',
                'mistral-small-latest',
                'ministral-14b-latest',
                'ministral-8b-latest',
                'ministral-3b-latest',
                'codestral-latest',
                'zai-glm-5-2',
            },
        )

    def test_image_model_seeded_as_the_provider_default(self):
        image = self.provider.default_image_model_id
        self.assertEqual(image.modality, 'image')
        self.assertEqual(image.technical_name, 'mistral-medium-latest')
        self.assertEqual(image.output_rate, 0.1)
        self.assertEqual(image._compute_usage_cost({'images': 2})['total_cost'], 0.2)

    def test_model_for_falls_back_to_default(self):
        self.assertEqual(
            self.provider._get_client().model_for(),
            'mistral-medium-latest',
        )

    # ----------------------------------------------------------
    # Capabilities
    # ----------------------------------------------------------

    def test_capabilities_are_on(self):
        self.assertTrue(self.provider.supports_web_search)
        self.assertTrue(self.provider.supports_code_interpreter)
