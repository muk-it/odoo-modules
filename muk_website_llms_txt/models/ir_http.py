import logging

from odoo import models
from odoo.http import request

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

    # ----------------------------------------------------------
    # Functions
    # ----------------------------------------------------------

    @classmethod
    def _post_dispatch(cls, response):
        super()._post_dispatch(response)
        if not cls._wants_markdown():
            return
        if not hasattr(request, 'website') or not request.website:
            return
        website = request.website
        if not website.llms_markdown_enabled:
            return
        content_type = response.headers.get('Content-Type', '')
        if 'text/html' not in content_type:
            return
        if response.status_code != 200:
            return
        try:
            from odoo.addons.muk_website_llms_txt.tools.converter import (
                html_to_markdown,
                estimate_tokens,
                build_content_signal,
            )
            html_content = response.get_data(as_text=True)
            markdown = html_to_markdown(html_content)
            if not markdown:
                return
            token_count = estimate_tokens(markdown)
            content_signal = build_content_signal(
                website.llms_content_signal or 'all'
            )
            response.set_data(markdown.encode('utf-8'))
            response.headers['Content-Type'] = 'text/markdown; charset=utf-8'
            response.headers['Vary'] = 'Accept'
            response.headers['x-markdown-tokens'] = str(token_count)
            response.headers['Content-Signal'] = content_signal
        except Exception:
            _logger.warning(
                "Failed to convert response to markdown",
                exc_info=True,
            )
