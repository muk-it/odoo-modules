import logging

from odoo import models
from odoo.http import request

from odoo.addons.muk_website_llms_txt.tools.converter import (
    page_to_agent_markdown,
    estimate_tokens,
    build_content_signal,
)

_logger = logging.getLogger(__name__)


class IrHttp(models.AbstractModel):

    _inherit = 'ir.http'

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    @classmethod
    def _wants_markdown(cls):
        if not request or not request.httprequest:
            return False
        accept = request.httprequest.headers.get('Accept', '')
        return 'text/markdown' in accept

    @classmethod
    def _can_convert_to_markdown(cls, response):
        return (
            cls._wants_markdown() and
            getattr(request, 'website', None) and
            response.status_code == 200 and
            'text/html' in response.headers.get('Content-Type', '')
        )

    @classmethod
    def _wants_link_headers(cls, response):
        website = getattr(request, 'website', None)
        return bool(
            website and
            website.llms_link_headers_enabled and
            response.status_code == 200 and
            'text/html' in response.headers.get('Content-Type', '')
        )

    @classmethod
    def _add_link_headers(cls, response):
        link = request.website._get_llms_link_header(
            request.httprequest.path
        )
        if not link:
            return
        response.headers.add('Link', link)
        vary = response.headers.get('Vary', '')
        if 'accept' not in vary.lower():
            response.headers['Vary'] = (
                '%s, Accept' % vary if vary else 'Accept'
            )

    @classmethod
    def _post_dispatch(cls, response):
        super()._post_dispatch(response)
        if cls._can_convert_to_markdown(response):
            try:
                markdown = page_to_agent_markdown(
                    response.get_data(as_text=True)
                )
                if markdown:
                    website = request.website
                    content_signal = build_content_signal(
                        website.llms_content_signal or 'all'
                    )
                    response.set_data(markdown.encode('utf-8'))
                    response.headers['Content-Type'] = 'text/markdown; charset=utf-8'
                    response.headers['Vary'] = 'Accept'
                    response.headers['x-markdown-tokens'] = str(
                        estimate_tokens(markdown)
                    )
                    response.headers['Content-Signal'] = content_signal
            except Exception:
                _logger.warning(
                    "Failed to convert response to markdown", exc_info=True,
                )
        if cls._wants_link_headers(response):
            try:
                cls._add_link_headers(response)
            except Exception:
                _logger.warning(
                    "Failed to add agent-discovery Link headers",
                    exc_info=True,
                )
