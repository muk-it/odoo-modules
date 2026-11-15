from __future__ import annotations

import json
from unittest.mock import MagicMock

from odoo import fields, models

from odoo.addons.muk_ai.tests.common import AITestCommon


def text_payload(text: str = 'ok') -> dict:
    """Build the provider result of a round that answers with plain text."""
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
        'usage': {'input_tokens': 4, 'output_tokens': 2},
    }


def tool_payload(*calls: tuple) -> dict:
    """Build the provider result of a round that makes ``(name, arguments, id)`` calls."""
    return {
        'text': '',
        'tool_calls': [
            {'call_id': call_id, 'name': name, 'arguments': arguments}
            for name, arguments, call_id in calls
        ],
        'carry_inputs': [
            {
                'type': 'function_call',
                'name': name,
                'arguments': json.dumps(arguments),
                'call_id': call_id,
            }
            for name, arguments, call_id in calls
        ],
        'usage': {'input_tokens': 4, 'output_tokens': 2},
    }


class BrowserTestCommon(AITestCommon):
    """Chats with a paired browser attached."""

    # ----------------------------------------------------------
    # Setup
    # ----------------------------------------------------------

    @classmethod
    def setUpClass(cls) -> None:
        """Lift the chat rate limit the table tests run into."""
        super().setUpClass()
        cls.provider.rate_limit = 0

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    def _session(self) -> models.BaseModel:
        """Create a chat owned by the current user."""
        return self.env['muk_ai.session'].create({'name': 'Test chat'})

    def _browser_chat(
        self, origin: str = 'https://shop.example.com'
    ) -> models.BaseModel:
        """Return a chat of the current user with a live browser on ``origin``."""
        key, _raw = self.env['muk_mcp.key']._pair_browser(self.env.user, 'Test')
        key.last_used = fields.Datetime.now()
        chat = self._session()
        chat._browser_attach(key)
        chat._browser_set_origin(origin)
        return chat

    def _rule(self, site: str, mode: str, user: models.BaseModel | None = None) -> None:
        """Create a site rule for ``user``, or for everyone when ``user`` is falsy."""
        self.env['muk_ai_browser.permission'].create(
            {'site': site, 'mode': mode, 'user_id': user.id if user else False}
        )

    def _stale(self, chat: models.BaseModel) -> None:
        """Make the chat's browser look gone."""
        chat.browser_key_id.last_used = fields.Datetime.subtract(
            fields.Datetime.now(), hours=1
        )

    def _tool_output(self, chat: models.BaseModel, call_id: str) -> dict:
        """Return the decoded tool output the conversation holds for ``call_id``."""
        [output] = [
            item
            for item in chat.conversation or []
            if isinstance(item, dict)
            and item.get('type') == 'function_call_output'
            and item.get('call_id') == call_id
        ]
        return json.loads(output['output'])

    def _request(self, mock: MagicMock, index: int = 0) -> dict:
        """Return the keyword arguments of the ``index``-th provider request."""
        return mock.call_args_list[index].kwargs

    def _system_prompt(self, request: dict) -> str:
        """Return the system prompt a provider request carries."""
        return request['inputs'][0]['content'][0]['text']

    def _tools(self, request: dict) -> set[str]:
        """Return the names of the tools a provider request offers the model."""
        return {tool['name'] for tool in request['tools_schema'] or []}
