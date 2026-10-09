from __future__ import annotations

from contextlib import closing
from unittest.mock import patch

from odoo import models
from odoo.tools.safe_eval import safe_eval

from odoo.addons.muk_ai.tests.common import (
    AITestCommon,
    PNG_1x1,
    json_response,
    text_payload,
)
from odoo.addons.muk_ai.tools.runtime import DEFAULT_CONTEXT_WINDOW


class TestModelResolution(AITestCommon):
    """Verify the model an agent and its chats run each modality on."""

    # ----------------------------------------------------------
    # Setup
    # ----------------------------------------------------------

    @classmethod
    def setUpClass(cls) -> None:
        """Keep only the shipped providers, each with its own models, and a keyless one."""
        super().setUpClass()
        shipped = cls.provider | cls.provider_anthropic | cls.provider_google
        (cls.env['muk_ai.provider'].search([]) - shipped).active = False
        cls.chat_openai = cls._catalog(cls.provider, 'gpt-res-chat', window=300000)
        cls.image_openai = cls._catalog(cls.provider, 'gpt-res-image', 'image')
        cls.chat_anthropic = cls._catalog(cls.provider_anthropic, 'claude-res-chat')
        cls.image_anthropic = cls._catalog(
            cls.provider_anthropic, 'claude-res-image', 'image'
        )
        cls.chat_google = cls._catalog(cls.provider_google, 'gemini-res-chat')
        cls.image_google = cls._catalog(
            cls.provider_google, 'gemini-res-image', 'image'
        )
        cls.keyless = cls.env['muk_ai.provider'].create(
            {'name': 'openai', 'code': 'keyless', 'sequence': 50}
        )
        cls.chat_keyless = cls._catalog(cls.keyless, 'gpt-res-keyless')
        for provider, sequence, chat, image in (
            (cls.provider, 10, cls.chat_openai, cls.image_openai),
            (cls.provider_anthropic, 20, cls.chat_anthropic, None),
            (cls.provider_google, 30, cls.chat_google, cls.image_google),
            (cls.keyless, 50, cls.chat_keyless, None),
        ):
            provider.write(
                {
                    'sequence': sequence,
                    'default_chat_model_id': chat.id,
                    'default_image_model_id': image and image.id,
                }
            )

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    @classmethod
    def _catalog(
        cls,
        provider: models.BaseModel,
        technical_name: str,
        modality: str = 'chat',
        window: int = 200000,
    ) -> models.BaseModel:
        """Create a catalogue model named after its technical name."""
        return cls.env['muk_ai.model'].create(
            {
                'name': technical_name,
                'provider_id': provider.id,
                'technical_name': technical_name,
                'modality': modality,
                'context_window': window if modality == 'chat' else 0,
                'input_rate': 1.0,
                'output_rate': 1.0,
            }
        )

    def _agent(self, writes: tuple, **values) -> models.BaseModel:
        """Apply the ``(record, values)`` writes, then create an agent."""
        for record, vals in writes:
            record.write(vals)
        return self.env['muk_ai.agent'].create({'name': 'Resolver', **values})

    def _assert_warning(self, agent: models.BaseModel, fragment: str) -> None:
        """Assert the agent form warns with ``fragment``, or not at all when empty."""
        if fragment:
            self.assertIn(fragment, agent.capability_warning)
        else:
            self.assertFalse(agent.capability_warning)

    # ----------------------------------------------------------
    # Tests
    # ----------------------------------------------------------

    def test_the_chat_model_follows_the_pick_the_pin_and_the_walk(self):
        none = self.env['muk_ai.model']
        pin = {'provider_id': self.provider_anthropic.id}
        cleared = tuple(
            (provider, {'default_chat_model_id': False})
            for provider in (
                self.provider,
                self.provider_anthropic,
                self.provider_google,
                self.keyless,
            )
        )
        for writes, values, expected, default, warning in (
            ((), {}, self.chat_openai, self.chat_openai, ''),
            ((), pin, self.chat_anthropic, self.chat_anthropic, ''),
            (
                (),
                {**pin, 'model_id': self.chat_openai.id},
                self.chat_openai,
                self.chat_anthropic,
                'so it overrides the pinned provider',
            ),
            (
                (),
                {**pin, 'model_id': self.chat_anthropic.id},
                self.chat_anthropic,
                self.chat_anthropic,
                '',
            ),
            (
                ((self.provider_anthropic, {'default_chat_model_id': False}),),
                pin,
                self.chat_openai,
                self.chat_openai,
                '',
            ),
            (
                ((self.chat_anthropic, {'active': False}),),
                pin,
                self.chat_openai,
                self.chat_openai,
                '',
            ),
            (
                ((self.chat_anthropic, {'active': False}),),
                {'model_id': self.chat_anthropic.id},
                self.chat_openai,
                self.chat_openai,
                'is archived, so this agent falls back to the default model',
            ),
            (
                (),
                {'provider_id': self.keyless.id},
                self.chat_keyless,
                self.chat_keyless,
                'pinned to OpenAI (keyless), which has no API key configured',
            ),
            (
                (
                    (self.keyless, {'sequence': 1}),
                    (self.env.company, {'default_ai_provider_id': False}),
                ),
                {},
                self.chat_openai,
                self.chat_openai,
                '',
            ),
            (
                ((self.provider, {'api_key': False}),),
                {'model_id': self.chat_openai.id},
                self.chat_openai,
                self.chat_anthropic,
                'runs on OpenAI, which has no API key configured',
            ),
            (cleared, {}, none, None, ''),
        ):
            with self.subTest(values=values), closing(self.env.cr.savepoint()):
                agent = self._agent(writes, **values)
                self.assertEqual(agent._resolve_model_for('chat'), expected)
                self.assertEqual(
                    agent.model_placeholder,
                    f'Default: {default.display_name}'
                    if default
                    else 'No chat model available',
                )
                self._assert_warning(agent, warning)

    def test_the_image_model_follows_the_toggle_the_pick_and_the_walk(self):
        none = self.env['muk_ai.model']
        draw = {'enable_image_generation': True}
        no_openai = (self.provider, {'default_image_model_id': False})
        no_google = (self.provider_google, {'default_image_model_id': False})
        archived = ((self.image_google, {'active': False}),)
        for writes, values, expected, warning in (
            ((), draw, self.image_openai, ''),
            ((), {'image_model_id': self.image_google.id}, none, ''),
            (
                (),
                {**draw, 'image_model_id': self.image_google.id},
                self.image_google,
                '',
            ),
            ((), {**draw, 'model_id': self.chat_google.id}, self.image_google, ''),
            ((), {**draw, 'model_id': self.chat_anthropic.id}, self.image_openai, ''),
            (
                (no_openai,),
                {**draw, 'model_id': self.chat_anthropic.id},
                self.image_google,
                '',
            ),
            ((no_openai, no_google), draw, none, 'no image model resolves'),
            (
                (),
                {**draw, 'provider_id': self.provider_anthropic.id},
                self.image_openai,
                '',
            ),
            (
                (
                    (
                        self.provider_anthropic,
                        {'default_image_model_id': self.image_anthropic.id},
                    ),
                ),
                {**draw, 'provider_id': self.provider_anthropic.id},
                self.image_anthropic,
                '',
            ),
            (
                archived,
                {**draw, 'image_model_id': self.image_google.id},
                self.image_openai,
                'Image Model gemini-res-image (Google) is archived',
            ),
            (archived, {'image_model_id': self.image_google.id}, none, ''),
            (
                ((self.provider_google, {'api_key': False}), no_openai),
                {**draw, 'model_id': self.chat_google.id},
                none,
                'the image model it would draw with runs on Google',
            ),
        ):
            with self.subTest(values=values), closing(self.env.cr.savepoint()):
                agent = self._agent(writes, **values)
                self.assertEqual(agent._resolve_model_for('image'), expected)
                self._assert_warning(agent, warning)
        for writes, placeholder in (
            ((), f'Default: {self.image_openai.display_name}'),
            ((no_openai, no_google), 'No image model available'),
        ):
            with (
                self.subTest(placeholder=placeholder),
                closing(self.env.cr.savepoint()),
            ):
                agent = self._agent(writes)
                self.assertEqual(agent.image_model_placeholder, placeholder)

    def test_a_chat_runs_on_the_model_and_window_its_agent_resolves(self):
        cleared = tuple(
            (provider, {'default_chat_model_id': False})
            for provider in (
                self.provider,
                self.provider_anthropic,
                self.provider_google,
                self.keyless,
            )
        )
        for writes, values, model, window in (
            ((), {'model_id': self.chat_anthropic.id}, 'claude-res-chat', 200000),
            ((), {}, 'gpt-res-chat', 300000),
            (cleared, {}, None, DEFAULT_CONTEXT_WINDOW),
        ):
            with self.subTest(values=values), closing(self.env.cr.savepoint()):
                session = self._session(agent_id=self._agent(writes, **values).id)
                self.assertEqual(session.get_snapshot()['context_window'], window)
                with self._mock_responses([text_payload()]) as requests:
                    session.start('go')
                self.assertEqual(requests[0]['model'], model)

    def test_an_override_of_the_session_seam_moves_every_modality(self):
        wide = self._catalog(self.provider_google, 'gemini-res-wide', window=900000)
        picks = {'chat': wide, 'image': self.image_openai}
        session = self._session(
            agent_id=self._agent(
                (),
                model_id=self.chat_anthropic.id,
                enable_image_generation=True,
                image_model_id=self.image_google.id,
            ).id
        )
        env = self.env(context={**self.env.context, 'muk_mcp_session_id': session.id})
        with patch.object(
            type(session),
            '_resolve_model_for',
            lambda record, modality: picks[modality],
        ):
            window = session.get_snapshot()['context_window']
            with self._mock_responses([text_payload()]) as requests:
                session.start('go')
            with self._capture_post(
                json_response({'data': [{'b64_json': PNG_1x1}]})
            ) as posts:
                env['muk_mcp.tool']._call('generate_image', {'prompt': 'a dot'}, env)
        self.assertEqual(window, 900000)
        self.assertEqual(requests[0]['model'], 'gemini-res-wide')
        url, kwargs = posts[0]
        self.assertEqual(url, 'https://api.openai.com/v1/images/generations')
        self.assertEqual(kwargs['json']['model'], 'gpt-res-image')
        self.assertEqual(session.get_snapshot()['context_window'], 200000)

    def test_the_default_walk_skips_what_cannot_serve(self):
        none = self.env['muk_ai.model']
        everyone = (
            self.provider,
            self.provider_anthropic,
            self.provider_google,
            self.keyless,
        )
        keyless = tuple((provider, {'api_key': False}) for provider in everyone)
        lead = (
            self.env.company,
            {'default_ai_provider_id': self.provider_anthropic.id},
        )
        claude = self.chat_anthropic
        for writes, modality, kwargs, expected in (
            ((), 'chat', {}, self.chat_openai),
            ((lead,), 'chat', {}, claude),
            (((self.provider, {'default_chat_model_id': False}),), 'chat', {}, claude),
            (((self.provider, {'active': False}),), 'chat', {}, claude),
            (((self.chat_openai, {'active': False}),), 'chat', {}, claude),
            (((self.provider, {'api_key': False}),), 'chat', {}, claude),
            ((), 'chat', {'first': self.provider_google}, self.chat_google),
            (
                ((self.provider_google, {'api_key': False}),),
                'chat',
                {'first': self.provider_google},
                self.chat_openai,
            ),
            (
                (lead, (self.provider_anthropic, {'api_key': False})),
                'chat',
                {},
                self.chat_openai,
            ),
            (keyless, 'chat', {}, none),
            (keyless, 'chat', {'configured': False}, self.chat_openai),
            ((), 'image', {'first': self.provider_anthropic}, self.image_openai),
            (
                (
                    (self.provider, {'default_image_model_id': False}),
                    (self.provider_google, {'default_image_model_id': False}),
                ),
                'image',
                {},
                none,
            ),
        ):
            with (
                self.subTest(modality=modality, kwargs=kwargs),
                closing(self.env.cr.savepoint()),
            ):
                for record, vals in writes:
                    record.write(vals)
                self.assertEqual(
                    self.env['muk_ai.model']._default_for(modality, **kwargs),
                    expected,
                )

    def test_each_picker_offers_only_models_of_its_kind(self):
        provider_fields = self.env['muk_ai.provider']._fields
        agent_fields = self.env['muk_ai.agent']._fields
        scope = {'id': self.provider.id}
        for domain, offered, hidden in (
            (
                safe_eval(provider_fields['default_chat_model_id'].domain, scope),
                self.chat_openai,
                self.image_openai | self.chat_anthropic,
            ),
            (
                safe_eval(provider_fields['default_image_model_id'].domain, scope),
                self.image_openai,
                self.chat_openai | self.image_google,
            ),
            (
                agent_fields['model_id'].domain,
                self.chat_openai | self.chat_anthropic | self.chat_google,
                self.image_openai | self.image_google,
            ),
            (
                agent_fields['image_model_id'].domain,
                self.image_openai | self.image_google | self.image_anthropic,
                self.chat_openai | self.chat_google,
            ),
        ):
            with self.subTest(domain=domain):
                found = self.env['muk_ai.model'].search(domain)
                self.assertEqual(found & (offered | hidden), offered)
