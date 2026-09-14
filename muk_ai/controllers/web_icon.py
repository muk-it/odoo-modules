from __future__ import annotations

from odoo import http
from odoo.http import Response, request

from odoo.addons.muk_ai.tools import FAVICON_CACHE_SECONDS, FAVICON_ROUTE


class AIWebIconController(http.Controller):
    """Serve the favicons of cited web sources from this Odoo's own origin.

    Linking a site's own icon URL would announce every viewer's IP and, through
    the referrer, this Odoo's hostname to a third party.
    """

    # ----------------------------------------------------------
    # Routes
    # ----------------------------------------------------------

    @http.route(
        f'{FAVICON_ROUTE}/<string:domain>',
        type='http',
        auth='user',
        methods=['GET'],
        readonly=True,
    )
    def web_source_icon(self, domain: str, **kwargs) -> Response:
        """Serve the favicon cached for ``domain``, or 404 for the client's glyph.

        :raise NotFound: when the caller is not an internal user, or nothing
            usable is cached for the domain
        """
        if not request.env.user._is_internal():
            raise request.not_found()
        if (icon := request.env['muk_mcp.mixin']._ai_favicon(domain)) is None:
            raise request.not_found()
        body, mimetype = icon
        return request.make_response(
            body,
            headers=[
                ('Content-Type', mimetype),
                ('Content-Length', str(len(body))),
                ('Content-Disposition', 'inline'),
                ('Cache-Control', f'private, max-age={FAVICON_CACHE_SECONDS}'),
                ('Content-Security-Policy', "default-src 'none'"),
                ('X-Content-Type-Options', 'nosniff'),
            ],
        )
