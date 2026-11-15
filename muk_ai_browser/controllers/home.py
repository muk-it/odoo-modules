from __future__ import annotations

from typing import Any

from odoo import http
from odoo.http import Response, request

from odoo.addons.web.controllers import home


class Home(home.Home):
    """Let the user's paired browser extensions show the web client in their panel."""

    # ----------------------------------------------------------
    # Routes
    # ----------------------------------------------------------

    @http.route()
    def web_client(self, s_action: str | None = None, **kw: Any) -> Response:
        """Allow framing by Odoo itself and the extensions the user paired."""
        response = super().web_client(s_action=s_action, **kw)
        if origins := request.env['muk_mcp.key']._browser_extensions(request.env.user):
            response.headers.pop('X-Frame-Options', None)
            response.headers['Content-Security-Policy'] = 'frame-ancestors {}'.format(
                ' '.join(["'self'", *origins])
            )
        return response
