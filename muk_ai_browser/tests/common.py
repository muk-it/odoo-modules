from __future__ import annotations

import json
from contextlib import AbstractContextManager
from unittest.mock import patch

from odoo import models

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

    def _device_key(
        self,
        scope: str = 'write',
        label: str = 'Test Device',
    ) -> tuple[models.BaseModel, str]:
        """Mint a device key for the current user.

        :return: the ``muk_mcp.key`` record and its one-time plaintext
        """
        return self.env['muk_ai_browser.device']._mint(
            self.env.uid,
            label,
            scope=scope,
        )

    def _new_ai_session(self, name: str = 'browser') -> models.BaseModel:
        """Create a chat session owned by the current user."""
        return self.env['muk_ai.session'].create({'name': name})

    def _browser_session(
        self,
        ai_session: models.BaseModel | None = None,
        key: models.BaseModel | None = None,
        device_label: str = 'Test Device',
    ) -> models.BaseModel:
        """Attach a browser session, minting a device key when needed."""
        ai_session = ai_session or self._new_ai_session()
        if key is None:
            key, _raw = self._device_key()
        return self.env['muk_ai_browser.session']._attach(
            ai_session,
            key,
            device_label=device_label,
        )

    def _browser_events(
        self,
        browser_session: models.BaseModel,
    ) -> list[tuple[str, dict]]:
        """Return the queued ``(type, payload)`` events in sequence order."""
        records = self.env['muk_ai_browser.event'].search(
            [('browser_session_id', '=', browser_session.id)],
            order='seq asc',
        )
        return [(record.type, record.payload) for record in records]

    # ----------------------------------------------------------
    # Scripted provider
    # ----------------------------------------------------------

    def _tool_payload(
        self,
        name: str,
        arguments: dict,
        call_id: str,
    ) -> dict:
        """Build a provider response asking for one tool call."""
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

    def _text_payload(self, text: str) -> dict:
        """Build a provider response carrying a final assistant answer."""
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

    def _script_provider(
        self,
        payloads: list[dict],
    ) -> AbstractContextManager:
        """Patch the provider to return ``payloads`` one round at a time."""
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

    def _track_execute(self, calls: list) -> AbstractContextManager:
        """Patch server-side tool execution and record the names called."""

        def fake(self_arg, name, arguments, env, enforce_scope):
            calls.append(name)
            return 'server-ran', {}, arguments.get('model')

        return patch.object(
            type(self.env['muk_mcp.tool']),
            '_execute',
            autospec=True,
            side_effect=fake,
        )
