import json
from unittest.mock import patch

from odoo.addons.muk_ai.tests.common import AITestCommon

BROWSER_TOOL_NAMES = [
    'read_page',
    'click',
    'fill',
    'select_option',
    'press_key',
    'hover',
    'scroll',
    'navigate',
    'navigate_back',
    'wait_for',
    'screenshot',
]


class BrowserTestCommon(AITestCommon):
    """Shared fixtures for the browser bridge, transport and pairing tests."""

    # ----------------------------------------------------------
    # Fixtures
    # ----------------------------------------------------------

    def _device_key(self, scope='write', label='Test Device'):
        return self.env['muk_ai_browser.device']._mint(
            self.env.uid,
            label,
            scope=scope,
        )

    def _new_ai_session(self, name='browser'):
        return self.env['muk_ai.session'].create({'name': name})

    def _browser_session(self, ai_session=None, key=None, device_label='Test Device'):
        ai_session = ai_session or self._new_ai_session()
        if key is None:
            key, _raw = self._device_key()
        return self.env['muk_ai_browser.session']._attach(
            ai_session,
            key,
            device_label=device_label,
        )

    def _browser_events(self, browser_session):
        records = self.env['muk_ai_browser.event'].search(
            [('browser_session_id', '=', browser_session.id)],
            order='seq asc',
        )
        return [(record.type, record.payload) for record in records]

    # ----------------------------------------------------------
    # Scripted provider
    # ----------------------------------------------------------

    def _tool_payload(self, name, arguments, call_id):
        return {
            'text': '',
            'tool_calls': [
                {
                    'call_id': call_id,
                    'name': name,
                    'arguments': arguments,
                }
            ],
            'carry_inputs': [
                {
                    'type': 'function_call',
                    'name': name,
                    'arguments': json.dumps(arguments),
                    'call_id': call_id,
                }
            ],
            'usage': {'input_tokens': 4, 'output_tokens': 2},
        }

    def _text_payload(self, text):
        return {
            'text': text,
            'tool_calls': [],
            'carry_inputs': [
                {
                    'type': 'message',
                    'role': 'assistant',
                    'content': [{'type': 'output_text', 'text': text}],
                }
            ],
            'usage': {'input_tokens': 3, 'output_tokens': 1},
        }

    def _script_provider(self, payloads):
        queue = list(payloads)

        def fake(self_arg, *args, **kwargs):
            if queue:
                return queue.pop(0)
            msg = 'exhausted scripted provider responses'
            raise AssertionError(msg)

        return patch.object(
            type(self.provider),
            '_request_responses',
            autospec=True,
            side_effect=fake,
        )

    def _track_execute(self, calls):
        def fake(self_arg, name, arguments, env, enforce_scope):
            calls.append(name)
            return 'server-ran', {}, arguments.get('model')

        return patch.object(
            type(self.env['muk_mcp.tool']),
            '_execute',
            autospec=True,
            side_effect=fake,
        )
