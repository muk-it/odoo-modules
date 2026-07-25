from __future__ import annotations

import logging

from odoo import http
from odoo.http import Response, request

from odoo.addons.muk_website_llms_txt.tools.converter import build_content_signal

_logger = logging.getLogger(__name__)


class LlmsTxtController(http.Controller):
    """Serve the ``/llms.txt`` and ``/llms-full.txt`` discovery files."""

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    def _serve_llms_document(self, document: str) -> Response:
        """Stream the stored document of the current website.

        The document is served straight from its attachment, so a request
        never renders the catalog and repeat crawlers are answered with a
        conditional ``304`` instead of the whole body.

        :param document: the name of the route the document is served on
        :return: the streamed document response
        """
        attachment = request.website._get_llms_document(document)
        response = attachment._to_http_stream().get_response(
            as_attachment=False, max_age=3600
        )
        response.headers['Content-Type'] = 'text/plain; charset=utf-8'
        response.headers['x-markdown-tokens'] = attachment.description or '0'
        response.headers['Content-Signal'] = build_content_signal(
            request.website.llms_content_signal or 'all'
        )
        return response

    # ----------------------------------------------------------
    # Routes
    # ----------------------------------------------------------

    @http.route(
        '/llms.txt',
        type='http',
        auth='public',
        website=True,
        multilang=False,
        sitemap=False,
    )
    def llms_txt(self, **kwargs) -> Response:
        """Return the llms.txt index of published website content."""
        if not request.website.llms_txt_enabled:
            raise request.not_found()
        return self._serve_llms_document('llms.txt')

    @http.route(
        '/llms-full.txt',
        type='http',
        auth='public',
        website=True,
        multilang=False,
        sitemap=False,
    )
    def llms_full_txt(self, **kwargs) -> Response:
        """Return the llms-full.txt dump of all published page content."""
        if not request.website.llms_full_txt_enabled:
            raise request.not_found()
        return self._serve_llms_document('llms-full.txt')
