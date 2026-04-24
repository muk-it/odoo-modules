import json

from unittest.mock import patch

from odoo.tests import HttpCase, tagged


@tagged('post_install', '-at_install')
class TestChatTour(HttpCase):

    # ----------------------------------------------------------
    # Setup
    # ----------------------------------------------------------

    def setUp(self):
        super().setUp()
        admin = self.env.ref('base.user_admin')
        self.env['muk_ai.session'].sudo().search([
            ('user_id', '=', admin.id),
            ('name', '=', 'Renamed Chat'),
        ]).unlink()
        for provider in self.env['muk_ai.provider'].sudo().search([]):
            if not provider.api_key:
                provider.api_key = 'test-key'

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    def _tool_payload(self, name, arguments, call_id):
        return {
            'text': '',
            'tool_calls': [{
                'call_id': call_id,
                'name': name,
                'arguments': arguments,
            }],
            'carry_inputs': [{
                'type': 'function_call',
                'name': name,
                'arguments': json.dumps(arguments),
                'call_id': call_id,
            }],
            'usage': {'input_tokens': 4, 'output_tokens': 2},
        }

    def _text_payload(self, text):
        return {
            'text': text,
            'tool_calls': [],
            'carry_inputs': [{
                'type': 'message',
                'role': 'assistant',
                'content': [{'type': 'output_text', 'text': text}],
            }],
            'usage': {'input_tokens': 3, 'output_tokens': 1},
        }

    def _script_provider(self, payloads):
        queue = list(payloads)

        def fake(self_arg, *args, **kwargs):
            if queue:
                return queue.pop(0)
            raise AssertionError('exhausted scripted provider responses')

        return patch.object(
            type(self.env['muk_ai.provider']),
            '_request_responses',
            autospec=True,
            side_effect=fake,
        )

    def _script_tool_results(self, results):
        def fake(self_arg, name, arguments, env, enforce_scope=None):
            if name not in results:
                raise AssertionError(f'unscripted tool {name!r}')
            return results[name], {}

        return patch.object(
            type(self.env['muk_mcp.tool']),
            '_call',
            autospec=True,
            side_effect=fake,
        )

    # ----------------------------------------------------------
    # Tests
    # ----------------------------------------------------------

    def test_chat_sidebar_tour(self):
        self.start_tour(
            '/odoo/action-muk_ai.action_ai_chat',
            'muk_ai_chat_sidebar_tour',
            login='admin',
        )

    def test_chat_roundtrip_tour(self):
        provider_ctx = self._script_provider([
            self._tool_payload('search_read', {
                'model': 'ir.module.module',
                'domain': [['state', '=', 'installed']],
                'fields': ['name'],
            }, 'c0'),
            self._text_payload('You have a few installed modules.'),
        ])
        tool_ctx = self._script_tool_results({
            'search_read': '[{"name": "base"}, {"name": "web"}]',
        })
        with provider_ctx, tool_ctx:
            self.start_tour(
                '/odoo/action-muk_ai.action_ai_chat',
                'muk_ai_chat_roundtrip_tour',
                login='admin',
            )
