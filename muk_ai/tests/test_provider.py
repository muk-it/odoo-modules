from __future__ import annotations

from contextlib import closing

from psycopg2.errors import UniqueViolation

from odoo.exceptions import UserError, ValidationError
from odoo.tests import new_test_user
from odoo.tools import mute_logger

from odoo.addons.muk_ai import _post_init_hook
from odoo.addons.muk_ai.tests.common import AITestCommon, sse_response

PROMPT = [{'role': 'user', 'content': [{'type': 'input_text', 'text': 'hi'}]}]

PONG = [
    {'type': 'response.output_text.delta', 'delta': 'pong'},
    {'type': 'response.completed', 'response': {'output': [], 'usage': {}}},
]


class TestProvider(AITestCommon):
    """Verify provider accounts, their catalogue and the connection test."""

    # ----------------------------------------------------------
    # Tests
    # ----------------------------------------------------------

    def test_the_region_decides_where_requests_go(self):
        user = new_test_user(self.env, login='region-user')
        gateway = 'https://gateway.test/openai/v1'
        custom = {'api_region': 'custom', 'api_url': gateway}
        for values, caller, endpoint in (
            ({}, self.env.user, 'https://api.openai.com/v1'),
            ({'api_region': 'eu'}, self.env.user, 'https://eu.api.openai.com/v1'),
            ({'api_region': 'us'}, self.env.user, 'https://us.api.openai.com/v1'),
            (custom, self.env.user, gateway),
            (custom, user, gateway),
        ):
            with self.subTest(values=values, caller=caller.login):
                self.provider.write({'api_region': 'default', **values})
                self.assertEqual(self.provider.api_endpoint, endpoint)
                with self._capture_post(sse_response(PONG)) as posts:
                    result = self.provider.with_user(caller)._request_responses(
                        inputs=PROMPT
                    )
                self.assertEqual(posts[0][0], f'{endpoint}/responses')
                self.assertEqual(result['text'], 'pong')

    def test_inconsistent_settings_are_refused(self):
        provider = self.env['muk_ai.provider']
        other = self.provider_anthropic
        for label, change, error in (
            (
                'custom region without a URL',
                lambda: self.provider.write({'api_region': 'custom', 'api_url': ''}),
                ValidationError,
            ),
            (
                'region the vendor does not offer',
                lambda: other.write({'api_region': 'eu'}),
                ValidationError,
            ),
            (
                'two accounts with one code',
                lambda: provider.create([{'name': 'openai', 'code': 'twin'}] * 2),
                UniqueViolation,
            ),
            (
                'chat model without a context window',
                lambda: self._create_model('no-window', context_window=0),
                ValidationError,
            ),
            (
                'one name and modality twice on a provider',
                lambda: self._create_model('twice') | self._create_model('twice'),
                UniqueViolation,
            ),
            (
                'one name once per modality',
                lambda: (
                    self._create_model('dual')
                    | self._create_model('dual', modality='image')
                ),
                None,
            ),
            (
                'one name once per provider',
                lambda: (
                    self._create_model('shared')
                    | self._create_model('shared', provider=other)
                ),
                None,
            ),
        ):
            with self.subTest(label), mute_logger('odoo.sql_db'):
                if error:
                    with self.assertRaises(error), self.env.cr.savepoint():
                        change()
                else:
                    with closing(self.env.cr.savepoint()):
                        self.assertEqual(len(change()), 2)

    def test_only_providers_added_by_hand_can_be_deleted(self):
        admin = new_test_user(
            self.env, login='provider-admin', groups='base.group_system'
        )
        added = (
            self.env['muk_ai.provider']
            .with_user(admin)
            .create({'name': 'openai', 'code': 'disposable'})
        )
        for caller, provider, deleted in (
            (self.env.user, self.provider, False),
            (admin, self.provider_google, False),
            (admin, added, True),
        ):
            with self.subTest(caller=caller.login, provider=provider.display_name):
                if deleted:
                    provider.with_user(caller).unlink()
                else:
                    with self.assertRaisesRegex(UserError, 'Archive them instead'):
                        provider.with_user(caller).unlink()
                self.assertEqual(bool(provider.exists()), not deleted)

    def test_an_account_names_itself_and_its_models(self):
        second = self.env['muk_ai.provider'].create({'name': 'openai', 'code': 'eu'})
        self.assertFalse(second.model_modalities)
        chat = self._create_model('named', provider=second)
        drawn = self._create_model('drawn', modality='image', provider=second)
        for record, name in (
            (self.provider, 'OpenAI'),
            (second, 'OpenAI (eu)'),
            (self._create_model('named'), 'named (OpenAI)'),
            (chat, 'named (OpenAI (eu))'),
        ):
            with self.subTest(name=name):
                self.assertEqual(record.display_name, name)
        self.assertEqual(second.model_modalities, ['chat', 'image'])
        self.assertEqual(
            (chat.rate_unit, drawn.rate_unit), ('USD per M tokens', 'USD per image')
        )
        chat.active = False
        self.assertEqual(second.model_modalities, ['image'])

    def test_the_install_hook_seeds_only_missing_company_defaults(self):
        general = self.env.ref('muk_ai.agent_general')
        own = self.env['muk_ai.agent'].create({'name': 'Own'})
        bare, partial, configured = self.env['res.company'].create(
            [{'name': 'Bare'}, {'name': 'Partial'}, {'name': 'Configured'}]
        )
        partial.default_ai_provider_id = self.provider_anthropic
        configured.write(
            {
                'default_ai_provider_id': self.provider_google.id,
                'default_ai_agent_id': own.id,
            }
        )
        _post_init_hook(self.env)
        for company, provider, agent in (
            (bare, self.provider, general),
            (partial, self.provider_anthropic, general),
            (configured, self.provider_google, own),
        ):
            with self.subTest(company=company.name):
                self.assertEqual(company.default_ai_provider_id, provider)
                self.assertEqual(company.default_ai_agent_id, agent)
