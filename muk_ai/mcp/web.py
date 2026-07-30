from __future__ import annotations

import urllib3

from odoo import api, models
from odoo.exceptions import UserError

from ..tools import WEB_FETCH_MAX_CHARS, fetch_url, page_icon, render_content
from odoo.addons.muk_mcp.core.tool import mcp_tool


class AIWeb(models.AbstractModel):
    """Expose an SSRF-guarded web page fetch as an MCP tool."""

    _inherit = 'muk_mcp.mixin'

    # ----------------------------------------------------------
    # Functions
    # ----------------------------------------------------------

    @api.model
    @mcp_tool(
        name='web_fetch',
        description=(
            'Fetch a public web page and return its main content as Markdown, '
            'with the page title and final source URL. Boilerplate (nav, '
            'ads, scripts) is stripped; links and headings are preserved so '
            'you can read and cite the page. Use it to read a specific URL '
            'the user gave or that a web search surfaced, then cite the '
            'returned url as the source. Long pages are paginated: when the '
            'result is truncated, call again with the reported "offset" to '
            'read the next window. "mode" controls the output: "markdown" '
            '(default, main content as Markdown), "text" (main content as '
            'plain text), or "html" (unconverted source — use for JSON/text '
            'endpoints or when you need the raw markup). http:// is upgraded '
            'to https:// and only publicly routable hosts are allowed. For '
            'discovering pages across the web, use web search instead. '
            'AI-agent only.'
        ),
        input_schema={
            'type': 'object',
            'properties': {
                'url': {
                    'type': 'string',
                    'description': 'The URL to fetch (http:// is upgraded to https://).',
                },
                'offset': {
                    'type': 'integer',
                    'description': (
                        'Character offset to start from, for reading past a '
                        'previous truncation. Default 0.'
                    ),
                    'default': 0,
                },
                'max_chars': {
                    'type': 'integer',
                    'description': (
                        'Maximum characters to return in this call '
                        f'(1–{WEB_FETCH_MAX_CHARS}). Default {WEB_FETCH_MAX_CHARS}.'
                    ),
                    'default': WEB_FETCH_MAX_CHARS,
                },
                'mode': {
                    'type': 'string',
                    'enum': ['markdown', 'text', 'html'],
                    'description': (
                        'Output format: "markdown" (default), "text" (plain '
                        'text), or "html" (raw unconverted source).'
                    ),
                    'default': 'markdown',
                },
            },
            'required': ['url'],
        },
        category='read',
        registry='odoo',
    )
    def _mcp_web_fetch(
        self,
        url: str,
        offset: int = 0,
        max_chars: int = WEB_FETCH_MAX_CHARS,
        mode: str = 'markdown',
    ) -> dict:
        """Fetch ``url`` and return a paginated web source descriptor.

        :return: on success a ``{type, url, title, icon, content,
            content_type, bytes, total_chars, offset, next_offset,
            truncated}`` descriptor;
            on failure ``{url, error}`` so the model can react without the
            round aborting
        """
        if mode not in ('markdown', 'text', 'html'):
            mode = 'markdown'
        try:
            result = fetch_url(url)
        except (UserError, urllib3.exceptions.HTTPError) as exc:
            return {'url': url, 'error': str(exc)}
        title, content = render_content(result, mode=mode)
        icon = page_icon(result)
        total = len(content)
        offset = max(0, offset)
        max_chars = max(1, min(max_chars, WEB_FETCH_MAX_CHARS))
        window = content[offset : offset + max_chars]
        next_offset = offset + len(window)
        truncated = next_offset < total
        if offset >= total and total:
            window = f'[no content at offset {offset}; document has {total} characters]'
        elif truncated:
            window += (
                f'\n\n[truncated: characters {offset}–{next_offset} of {total}. '
                f'Call web_fetch again with offset={next_offset} for more.]'
            )
        return {
            'type': 'web',
            'url': result.url,
            'title': title,
            'icon': icon,
            'content': window,
            'content_type': result.content_type,
            'bytes': len(result.body),
            'total_chars': total,
            'offset': offset,
            'next_offset': next_offset if truncated else None,
            'truncated': truncated,
        }
