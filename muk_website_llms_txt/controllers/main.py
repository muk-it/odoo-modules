import logging

from odoo import http
from odoo.http import request

from odoo.addons.muk_website_llms_txt.tools.converter import (
    build_content_signal,
    estimate_tokens,
)

_logger = logging.getLogger(__name__)


class LlmsTxtController(http.Controller):

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
    def llms_txt(self, **kwargs):
        if not request.website.llms_txt_enabled:
            return request.not_found()
        content = request.website._get_llms_txt_content()
        token_count = estimate_tokens(content)
        content_signal = build_content_signal(
            request.website.llms_content_signal or 'all'
        )
        return request.make_response(content, [
            ('Content-Type', 'text/plain; charset=utf-8'),
            ('x-markdown-tokens', str(token_count)),
            ('Content-Signal', content_signal),
        ])

    @http.route(
        '/llms-full.txt',
        type='http',
        auth='public',
        website=True,
        multilang=False,
        sitemap=False,
    )
    def llms_full_txt(self, **kwargs):
        if not request.website.llms_full_txt_enabled:
            return request.not_found()
        content = request.website._get_llms_full_txt_content()
        token_count = estimate_tokens(content)
        content_signal = build_content_signal(
            request.website.llms_content_signal or 'all'
        )
        return request.make_response(content, [
            ('Content-Type', 'text/plain; charset=utf-8'),
            ('x-markdown-tokens', str(token_count)),
            ('Content-Signal', content_signal),
        ])
