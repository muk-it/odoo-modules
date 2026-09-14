from __future__ import annotations

import psycopg2

from odoo import models
from odoo.exceptions import UserError, ValidationError
from odoo.tools import mute_logger
from odoo.tools.safe_eval import safe_eval

from odoo.addons.muk_ai.tests.common import AITestCommon


class TestModality(AITestCommon):
    """Verify model modalities, per-modality defaults and rate dispatch."""

    # ----------------------------------------------------------
    # Setup
    # ----------------------------------------------------------

    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls.env.company.default_ai_provider_id = False
        cls.env['muk_ai.provider'].with_context(active_test=False).search(
            [
                (
                    'id',
                    'not in',
                    (cls.provider | cls.provider_anthropic | cls.provider_google).ids,
                )
            ],
        ).active = False
        cls.provider.sequence = 10
        cls.provider_anthropic.write({'active': True, 'sequence': 20})
        cls.provider_google.write({'active': True, 'sequence': 30})

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    def _make_model(
        self,
        technical_name: str,
        modality: str = 'chat',
        provider: models.BaseModel | None = None,
        **values,
    ) -> models.BaseModel:
        """Create a catalogue model of the modality, on ``self.provider`` by default."""
        return self.env['muk_ai.model'].create(
            {
                'name': technical_name,
                'provider_id': (provider or self.provider).id,
                'technical_name': technical_name,
                'modality': modality,
                'context_window': 128000 if modality == 'chat' else 0,
                'input_rate': 1.0,
                'output_rate': 2.0,
                **values,
            }
        )

    def _selectable(self, field_name: str) -> models.BaseModel:
        """Return the models the provider form offers for the given default field."""
        domain = safe_eval(
            self.env['muk_ai.provider']._fields[field_name].domain,
            {'id': self.provider.id},
        )
        return self.env['muk_ai.model'].search(domain)

    # ----------------------------------------------------------
    # Tests: constraints
    # ----------------------------------------------------------

    def test_same_technical_name_is_allowed_once_per_modality(self):
        chat = self._make_model('dual')
        image = self._make_model('dual', modality='image')
        self.assertEqual(chat.technical_name, image.technical_name)
        with (
            mute_logger('odoo.sql_db'),
            self.assertRaises(psycopg2.errors.UniqueViolation),
            self.env.cr.savepoint(),
        ):
            self._make_model('dual', modality='image')

    def test_context_window_is_only_required_for_chat(self):
        self.assertEqual(self._make_model('free', modality='image').context_window, 0)
        with self.assertRaises(ValidationError):
            self._make_model('zero-ctx', context_window=0)

    # ----------------------------------------------------------
    # Tests: default resolution
    # ----------------------------------------------------------

    def test_default_model_domains_scope_to_own_models_of_the_modality(self):
        chat = self._make_model('own-chat')
        image = self._make_model('own-image', modality='image')
        theirs = self._make_model('their-chat', provider=self.provider_anthropic)
        chat_choices = self._selectable('default_chat_model_id')
        image_choices = self._selectable('default_image_model_id')
        self.assertIn(chat, chat_choices)
        self.assertNotIn(image, chat_choices)
        self.assertNotIn(theirs, chat_choices)
        self.assertIn(image, image_choices)
        self.assertNotIn(chat, image_choices)

    def test_default_model_reads_the_modality_field(self):
        image = self._make_model('default-image', modality='image')
        self.provider.default_image_model_id = image
        self.assertEqual(self.provider._default_model('image'), image)
        self.assertEqual(
            self.provider._default_model('chat'),
            self.provider.default_chat_model_id,
        )

    def test_default_for_prefers_the_company_default_provider(self):
        self.env.company.default_ai_provider_id = self.provider_anthropic
        expected = self.provider_anthropic.default_chat_model_id
        self.assertTrue(expected)
        self.assertEqual(self.env['muk_ai.model']._default_for('chat'), expected)

    def test_default_for_walks_active_providers_by_sequence(self):
        Model = self.env['muk_ai.model']
        openai = self.provider.default_chat_model_id
        anthropic = self.provider_anthropic.default_chat_model_id
        google = self.provider_google.default_chat_model_id
        self.assertTrue(openai and anthropic and google)
        self.assertEqual(Model._default_for('chat'), openai)
        self.provider.default_chat_model_id = False
        self.assertEqual(Model._default_for('chat'), anthropic)
        self.provider_anthropic.active = False
        self.assertEqual(Model._default_for('chat'), google)

    def test_default_for_skips_an_archived_default(self):
        openai = self.provider.default_chat_model_id
        self.assertTrue(openai)
        openai.active = False
        self.env.invalidate_all()
        self.assertFalse(self.provider._default_model('chat'))
        self.assertEqual(
            self.env['muk_ai.model']._default_for('chat'),
            self.provider_anthropic.default_chat_model_id,
        )

    def test_default_for_walks_past_a_provider_without_credentials(self):
        Model = self.env['muk_ai.model']
        self.assertEqual(
            Model._default_for('chat'), self.provider.default_chat_model_id
        )
        self.provider.sudo().api_key = False
        self.env.invalidate_all()
        self.assertFalse(self.provider._can_serve())
        self.assertEqual(
            Model._default_for('chat'),
            self.provider_anthropic.default_chat_model_id,
        )

    def test_default_for_walks_past_a_keyless_lead_provider(self):
        self.provider_google.sudo().api_key = False
        self.env.invalidate_all()
        self.assertEqual(
            self.env['muk_ai.model']._default_for('chat', first=self.provider_google),
            self.provider.default_chat_model_id,
        )

    def test_default_for_walks_past_a_keyless_company_default(self):
        self.env.company.default_ai_provider_id = self.provider_anthropic
        self.provider_anthropic.sudo().api_key = False
        self.env.invalidate_all()
        self.assertEqual(
            self.env['muk_ai.model']._default_for('chat'),
            self.provider.default_chat_model_id,
        )

    def test_default_for_is_empty_when_nothing_holds_credentials(self):
        for provider in self.provider | self.provider_anthropic | self.provider_google:
            provider.sudo().api_key = False
        self.env.invalidate_all()
        self.assertFalse(self.env['muk_ai.model']._default_for('chat'))

    def test_default_for_can_walk_past_the_credential_check(self):
        for provider in self.provider | self.provider_anthropic | self.provider_google:
            provider.sudo().api_key = False
        self.env.invalidate_all()
        self.assertEqual(
            self.env['muk_ai.model']._default_for('chat', configured=False),
            self.provider.default_chat_model_id,
        )

    def test_an_explicit_pick_is_never_swapped_for_another_vendor(self):
        agent = self.env['muk_ai.agent'].create(
            {'name': 'Pinned', 'model_id': self.provider.default_chat_model_id.id}
        )
        self.provider.sudo().api_key = False
        self.env.invalidate_all()
        self.assertEqual(
            agent._resolve_model_for('chat'),
            self.provider.default_chat_model_id,
        )
        self.assertIn('has no API key configured', agent.capability_warning)
        with self.assertRaises(UserError) as caught:
            self.provider._get_client().headers()
        self.assertIn('API key is not configured', str(caught.exception))

    def test_default_for_is_empty_without_any_default(self):
        self._clear_default_models('image')
        self.assertFalse(self.env['muk_ai.model']._default_for('image'))

    def test_agent_model_domain_excludes_non_chat_models(self):
        image = self._make_model('agent-image', modality='image')
        chat = self._make_model('agent-chat')
        domain = self.env['muk_ai.agent']._fields['model_id'].domain
        selectable = self.env['muk_ai.model'].search(domain)
        self.assertIn(chat, selectable)
        self.assertNotIn(image, selectable)

    def test_agent_image_model_domain_offers_every_image_model(self):
        openai_image = self._make_model('openai-image', modality='image')
        chat = self._make_model('openai-chat')
        google_image = self._make_model(
            'google-image', modality='image', provider=self.provider_google
        )
        domain = self.env['muk_ai.agent']._fields['image_model_id'].domain
        selectable = self.env['muk_ai.model'].search(domain)
        self.assertIn(openai_image, selectable)
        self.assertIn(google_image, selectable)
        self.assertIn(self.env.ref('muk_ai.model_gemini_3_1_flash_image'), selectable)
        self.assertNotIn(chat, selectable)

    def test_default_for_leads_with_the_given_provider(self):
        Model = self.env['muk_ai.model']
        google = self.provider_google.default_chat_model_id
        self.assertEqual(
            Model._default_for('chat'), self.provider.default_chat_model_id
        )
        self.assertEqual(Model._default_for('chat', first=self.provider_google), google)
        self._clear_default_models('image')
        image = self._make_model('walked-image', modality='image')
        self.provider.default_image_model_id = image
        self.assertFalse(self.provider_anthropic.default_image_model_id)
        self.assertEqual(
            Model._default_for('image', first=self.provider_anthropic), image
        )

    def test_display_name_carries_the_provider(self):
        self.assertEqual(self._make_model('named').display_name, 'named (OpenAI)')
        account = self.env['muk_ai.provider'].create({'name': 'openai', 'code': 'eu'})
        self.assertEqual(
            self._make_model('second', provider=account).display_name,
            'second (OpenAI (eu))',
        )

    # ----------------------------------------------------------
    # Tests: capabilities
    # ----------------------------------------------------------

    def test_model_modalities_list_what_the_provider_covers(self):
        account = self.env['muk_ai.provider'].create({'name': 'google', 'code': 'test'})
        self.assertFalse(account.model_modalities)
        self._make_model('covered-chat', provider=account)
        self._make_model('covered-image', modality='image', provider=account)
        self.assertEqual(account.model_modalities, ['chat', 'image'])

    # ----------------------------------------------------------
    # Tests: rates
    # ----------------------------------------------------------

    def test_rate_unit_per_modality(self):
        self.assertEqual(self._make_model('unit-chat').rate_unit, 'USD per M tokens')
        self.assertEqual(
            self._make_model('unit-image', modality='image', currency='EUR').rate_unit,
            'EUR per image',
        )

    def test_usage_cost_chat_bills_tokens(self):
        record = self._make_model('cost-chat', input_rate=1.0, output_rate=2.0)
        cost = record._compute_usage_cost(
            {'input_tokens': 1_000_000, 'output_tokens': 500_000},
        )
        self.assertAlmostEqual(cost['input_cost'], 1.0)
        self.assertAlmostEqual(cost['output_cost'], 1.0)
        self.assertAlmostEqual(cost['total_cost'], 2.0)

    def test_usage_cost_image_bills_per_image(self):
        record = self._make_model('cost-image', modality='image', output_rate=0.05)
        cost = record._compute_usage_cost(
            {'images': 3, 'input_tokens': 1_000_000, 'output_tokens': 1_000_000},
        )
        self.assertAlmostEqual(cost['input_cost'], 0.0)
        self.assertAlmostEqual(cost['output_cost'], 0.15)
        self.assertAlmostEqual(cost['total_cost'], 0.15)
