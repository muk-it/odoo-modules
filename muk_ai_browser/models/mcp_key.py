from __future__ import annotations

import json

from odoo import api, fields, models
from odoo.fields import Domain
from odoo.http import request


class MCPKey(models.Model):
    """Mark the API keys that paired browsers authenticate with."""

    _inherit = 'muk_mcp.key'

    # ----------------------------------------------------------
    # Fields
    # ----------------------------------------------------------

    browser = fields.Boolean(
        string='Browser',
        help='The key was issued to a browser extension by pairing.',
        readonly=True,
    )

    browser_extension = fields.Char(
        string='Browser Extension',
        help='Origin of the paired extension, allowed to show the chat in its panel.',
        readonly=True,
    )

    browser_tabs = fields.Json(
        string='Browser Tabs',
        help='Tabs of the agent in the browser, as ids and origins.',
        readonly=True,
        copy=False,
    )

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    @api.model
    def _authenticate_domain(self) -> Domain:
        """Accept a browser key only on the routes of the browser extension."""
        domain = super()._authenticate_domain()
        if request and not request.httprequest.path.startswith('/muk_ai_browser/'):
            domain &= Domain('browser', '=', False)
        return domain

    # ----------------------------------------------------------
    # Functions
    # ----------------------------------------------------------

    @api.model
    def _pair_browser(
        self, user: models.BaseModel, label: str, origin: str | None = None
    ) -> tuple[MCPKey, str]:
        """Issue a browser key for ``user``, replacing the extension's earlier key.

        :return: the key record and its plaintext, which is never stored
        """
        extension = (
            origin if (origin or '').startswith('chrome-extension://') else False
        )
        if extension:
            self.sudo().search(
                [
                    ('user_id', '=', user.id),
                    ('browser', '=', True),
                    ('browser_extension', '=', extension),
                ],
            ).unlink()
        key, raw = self.with_user(user)._generate(label, 'write', 0)
        key.write({'browser': True, 'browser_extension': extension})
        return key, raw

    def _browser_set_tabs(self, tabs: str | None) -> None:
        """Record the agent's tabs the browser reports as JSON ids and origins."""
        try:
            reported = json.loads(tabs or '[]')
        except ValueError:
            return
        if not isinstance(reported, list):
            return
        origin_of = self.env['muk_ai.session']._browser_origin_of
        known = [
            {'id': tab['id'], 'origin': origin_of(tab.get('origin'))}
            for tab in reported[:50]
            if isinstance(tab, dict) and isinstance(tab.get('id'), int)
        ]
        if known != (self.browser_tabs or []):
            self.sudo().browser_tabs = known

    @api.model
    def _browser_extensions(self, user: models.BaseModel) -> list[str]:
        """Return the origins of the extensions ``user`` paired and did not revoke."""
        return (
            self.sudo()
            .search(
                [
                    ('user_id', '=', user.id),
                    ('browser', '=', True),
                    ('browser_extension', '!=', False),
                ],
            )
            .mapped('browser_extension')
        )
