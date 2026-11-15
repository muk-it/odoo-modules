from __future__ import annotations

import json
from unittest.mock import MagicMock

from odoo import fields, models

from odoo.addons.muk_ai.tests.common import AITestCommon


class BrowserTestCommon(AITestCommon):
    """Chats with a paired browser attached."""

    # ----------------------------------------------------------
    # Setup
    # ----------------------------------------------------------

    @classmethod
    def setUpClass(cls) -> None:
        """Let the tests start as many chats a minute as they need."""
        super().setUpClass()
        cls.provider.rate_limit = 0

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    def _session(self) -> models.BaseModel:
        """Create a chat session owned by the current user."""
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
        return next(
            json.loads(item['output'])
            for item in chat.conversation or []
            if isinstance(item, dict)
            and item.get('type') == 'function_call_output'
            and item.get('call_id') == call_id
        )

    @staticmethod
    def _requests(mock: MagicMock) -> list[dict]:
        """Return the keyword arguments of every provider request ``mock`` served."""
        return [call.kwargs for call in mock.call_args_list]

    @staticmethod
    def _system_prompt(request: dict) -> str:
        """Return the system prompt a provider request carries."""
        return '\n'.join(
            block['text']
            for item in request['inputs']
            if item.get('role') == 'system'
            for block in item['content']
        )

    @staticmethod
    def _tools(request: dict) -> set[str]:
        """Return the names of the tools a provider request offers the model."""
        return {tool['name'] for tool in request['tools_schema'] or []}
