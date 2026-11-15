from __future__ import annotations

from odoo import fields, models

from odoo.addons.muk_ai.tests.common import AITestCommon


class BrowserTestCommon(AITestCommon):
    """Chats with a paired browser attached."""

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

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
