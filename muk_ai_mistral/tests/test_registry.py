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
            self.provider.default_model_id.technical_name,
            'mistral-medium-latest',
        )

    def test_models_seeded_for_provider(self):
        models = self.env['muk_ai.model'].search(
            [
                ('provider_id', '=', self.provider.id),
            ]
        )
        self.assertEqual(len(models), 10)
        technical_names = set(models.mapped('technical_name'))
        self.assertIn('mistral-large-latest', technical_names)
        self.assertIn('codestral-latest', technical_names)
        self.assertIn('magistral-medium-latest', technical_names)

    def test_resolve_model_name_falls_back_to_default(self):
        self.assertEqual(
            self.provider._resolve_model_name(),
            'mistral-medium-latest',
        )

    # ----------------------------------------------------------
    # Capabilities
    # ----------------------------------------------------------

    def test_capabilities_are_on(self):
        self.assertTrue(self.provider.supports_web_search)
        self.assertTrue(self.provider.supports_image_generation)
        self.assertTrue(self.provider.supports_code_interpreter)
