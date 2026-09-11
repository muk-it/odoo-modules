from __future__ import annotations

from contextlib import AbstractContextManager
from unittest.mock import patch

import requests
from psycopg2.errors import UniqueViolation

from odoo.exceptions import UserError, ValidationError
from odoo.tests.common import new_test_user
from odoo.tools import mute_logger

from odoo.addons.muk_ai.providers import REGISTRY
from odoo.addons.muk_ai.providers.openai import OpenAIProvider
from odoo.addons.muk_ai.providers.region import CUSTOM, Region
from odoo.addons.muk_ai.tests.common import AITestCommon

RESTRICTED = Region(
    'restricted',
    'Restricted',
    'https://restricted.test/v1',
    disabled=('web_search', 'image_generation'),
)


class TestAiProviderRegion(AITestCommon):
    """Verify endpoint region presets, custom URLs and their constraints."""

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    def _patch_regions(self, *regions: Region) -> AbstractContextManager:
        """Swap the OpenAI region declarations for the given test regions."""
        return patch.object(OpenAIProvider, 'regions', regions)

    # ----------------------------------------------------------
    # Tests
    # ----------------------------------------------------------

    def test_default_region_uses_the_implementation_url(self):
        self.assertEqual(self.provider.api_region, 'default')
        self.assertEqual(
            self.provider._get_client().api_url,
            'https://api.openai.com/v1',
        )

    def test_region_the_implementation_lacks_is_reseeded(self):
        self.provider.api_region = 'eu'
        self.provider._compute_api_region()
        self.assertEqual(self.provider.api_region, 'eu')
        record = self.env['muk_ai.provider'].new({'name': 'openai', 'api_region': 'eu'})
        record.name = 'anthropic'
        self.assertEqual(record.api_region, 'default')

    def test_unregistered_implementation_seeds_from_the_stored_url(self):
        with patch.dict(REGISTRY, clear=True):
            self.provider.api_region = False
            self.provider._compute_api_region()
            self.assertEqual(self.provider.api_region, 'default')
            self.provider.write(
                {'api_region': False, 'api_url': 'https://gateway.test/openai/v1'}
            )
            self.provider._compute_api_region()
            self.assertEqual(self.provider.api_region, 'custom')

    def test_region_preset_resolves_to_its_url(self):
        self.provider.api_region = 'eu'
        self.assertEqual(
            self.provider._get_client().api_url,
            'https://eu.api.openai.com/v1',
        )

    def test_custom_region_resolves_to_the_record_url(self):
        self.provider.write(
            {'api_region': 'custom', 'api_url': 'https://gateway.test/openai/v1'}
        )
        self.assertEqual(
            self.provider._get_client().api_url,
            'https://gateway.test/openai/v1',
        )

    def test_custom_region_requires_a_url(self):
        with self.assertRaises(ValidationError):
            self.provider.write({'api_region': 'custom', 'api_url': False})

    def test_region_outside_the_options_is_rejected(self):
        with self.assertRaises(ValidationError):
            self.provider_anthropic.api_region = 'eu'

    def test_region_options_follow_the_declarations(self):
        self.assertFalse(self.provider_anthropic.api_region_options)
        self.assertFalse(self.provider_google.api_region_options)
        self.assertEqual(
            self.provider.api_region_options,
            ['default', 'eu', 'us', 'mtls-eu', 'custom'],
        )

    def test_endpoint_reflects_the_resolved_url(self):
        self.assertEqual(self.provider.api_endpoint, 'https://api.openai.com/v1')
        self.provider.api_region = 'us'
        self.assertEqual(self.provider.api_endpoint, 'https://us.api.openai.com/v1')

    def test_region_disables_capabilities(self):
        with self._patch_regions(RESTRICTED, CUSTOM):
            self.provider.api_region = 'restricted'
            self.assertFalse(self.provider.supports_web_search)
            self.assertFalse(self.provider.supports_image_generation)
            self.assertTrue(self.provider.supports_code_interpreter)
            self.provider.api_region = 'default'
            self.assertTrue(self.provider.supports_web_search)
            self.assertTrue(self.provider.supports_image_generation)

    def test_agent_capabilities_follow_the_provider_region(self):
        model = self._create_model('gpt-region')
        agent = self.env['muk_ai.agent'].create(
            {'name': 'Regional', 'model_id': model.id, 'enable_web_search': True}
        )
        self.assertTrue(agent.enable_web_search)
        with self._patch_regions(RESTRICTED, CUSTOM):
            self.provider.api_region = 'restricted'
            self.assertFalse(agent.supports_web_search)
            self.assertFalse(agent.enable_web_search)

    def test_display_name_carries_a_non_default_code(self):
        second = self.env['muk_ai.provider'].create({'name': 'openai', 'code': 'eu'})
        self.assertEqual(self.provider.display_name, 'OpenAI')
        self.assertEqual(second.display_name, 'OpenAI (eu)')

    def test_name_and_code_are_unique_together(self):
        self.env['muk_ai.provider'].create({'name': 'openai', 'code': 'second'})
        with mute_logger('odoo.sql_db'), self.assertRaises(UniqueViolation):
            self.env['muk_ai.provider'].create({'name': 'openai', 'code': 'second'})

    def test_a_shipped_provider_cannot_be_deleted(self):
        shipped = self.env.ref('muk_ai.provider_openai')
        with self.assertRaises(UserError):
            shipped.unlink()
        self.assertTrue(shipped.exists())

    def test_a_user_created_provider_can_be_deleted(self):
        provider = self.env['muk_ai.provider'].create(
            {'name': 'openai', 'code': 'disposable'}
        )
        provider.unlink()
        self.assertFalse(provider.exists())

    def test_admin_creates_and_unlinks_providers(self):
        admin = new_test_user(
            self.env, login='region_admin', groups='base.group_system'
        )
        provider = (
            self.env['muk_ai.provider']
            .with_user(admin)
            .create({'name': 'openai', 'code': 'admin'})
        )
        provider.unlink()
        self.assertFalse(provider.exists())

    def test_plain_user_request_reaches_the_custom_endpoint(self):
        self.provider.write(
            {'api_region': 'custom', 'api_url': 'https://gateway.test/openai/v1'}
        )
        user = new_test_user(self.env, login='region_user', groups='base.group_user')
        captured = {}

        def fake_post(url, **kwargs):
            captured['url'] = url
            return self._mock_http_response(
                {
                    'output': [{'type': 'message', 'content': [{'text': 'ok'}]}],
                    'usage': {'input_tokens': 1, 'output_tokens': 1},
                }
            )

        with patch.object(requests.Session, 'post', side_effect=fake_post):
            result = self.provider.with_user(user)._request_responses(
                inputs=[
                    {'role': 'user', 'content': [{'type': 'input_text', 'text': 'hi'}]}
                ],
            )
        self.assertEqual(captured['url'], 'https://gateway.test/openai/v1/responses')
        self.assertEqual(result['text'], 'ok')
