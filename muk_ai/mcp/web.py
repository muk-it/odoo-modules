from __future__ import annotations

import logging
from collections.abc import Iterable
from datetime import timedelta
from time import monotonic

import urllib3

from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.tools.mimetypes import guess_mimetype

from odoo.addons.muk_ai.tools import (
    FAVICON_BUDGET,
    FAVICON_DEADLINE,
    FAVICON_GC_BATCH,
    FAVICON_MAX_AGE_DAYS,
    FAVICON_MAX_BYTES,
    FAVICON_MIMETYPES,
    FAVICON_ROUTE,
    FRESHNESS_DAYS,
    WEB_FETCH_MAX_CHARS,
    WEB_SEARCH_MAX_RESULTS,
    SearchQuery,
    fetch_url,
    page_icon,
    render_content,
    search_backend,
    web_domain,
)
from odoo.addons.muk_mcp.core.tool import mcp_tool

_logger = logging.getLogger(__name__)


class AIWeb(models.AbstractModel):
    """Expose web search and an SSRF-guarded web page fetch as MCP tools."""

    _inherit = 'muk_mcp.mixin'

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    @api.model
    def _ai_store_favicon(self, domain: str, hint: str) -> None:
        """Cache the favicon of one domain, empty when it cannot be served.

        An empty attachment is the negative cache: the domain counts as
        cached, so a later search does not refetch it, and the route 404s.
        """
        body, mimetype = b'', ''
        url = hint or f'https://{domain}/favicon.ico'
        try:
            result = fetch_url(
                url, max_bytes=FAVICON_MAX_BYTES, deadline=FAVICON_DEADLINE
            )
        except (UserError, OSError, urllib3.exceptions.HTTPError) as exc:
            _logger.info('No favicon for %s: %s', domain, exc)
        else:
            sniffed = guess_mimetype(result.body, default='')
            if result.body and sniffed in FAVICON_MIMETYPES:
                body, mimetype = result.body, sniffed
            else:
                _logger.info(
                    'Refusing the favicon of %s: %s is not an accepted image type.',
                    domain,
                    sniffed or 'unknown',
                )
        self.env['ir.attachment'].sudo().create(
            {
                'name': f'muk_ai.favicon.{domain}',
                'type': 'binary',
                'url': f'{FAVICON_ROUTE}/{domain}',
                'mimetype': mimetype,
                'raw': body,
            }
        )

    @api.model
    def _ai_cache_favicons(
        self, targets: Iterable[tuple[str, str | None]]
    ) -> dict[str, str]:
        """Cache the favicon of every newly cited domain, once, within a budget.

        :param targets: ``(page url, declared icon url)`` pairs
        :return: each cited domain mapped to the local URL its icon is served
            from, whether or not this call had the budget left to fetch it
        """
        hints: dict[str, str] = {}
        for url, icon_url in targets:
            if domain := web_domain(url or ''):
                hints[domain] = hints.get(domain) or (icon_url or '')
        routes = {domain: f'{FAVICON_ROUTE}/{domain}' for domain in hints}
        attachments = self.env['ir.attachment'].sudo()
        cached = attachments.search([('url', 'in', list(routes.values()))]).mapped(
            'url'
        )
        expires = monotonic() + FAVICON_BUDGET
        for domain, route in routes.items():
            if route not in cached and monotonic() < expires:
                self._ai_store_favicon(domain, hints[domain])
        return routes

    @api.model
    def _ai_favicon(self, domain: str) -> tuple[bytes, str] | None:
        """Return the cached favicon of ``domain`` as ``(bytes, mimetype)``.

        :return: ``None`` when nothing was cached for the domain or what was
            cached carries no bytes, so the client falls back to its glyph
        """
        attachments = self.env['ir.attachment'].sudo()
        cached = attachments.search(
            [('url', '=', f'{FAVICON_ROUTE}/{domain}')], limit=1
        )
        if not (body := cached.raw):
            return None
        return body, cached.mimetype

    # ----------------------------------------------------------
    # Functions
    # ----------------------------------------------------------

    @api.model
    @mcp_tool(
        name='web_search',
        description=(
            'Search the public web and return up to 10 results, each with '
            'its url, title, snippet, domain and publication date when '
            'known. Use it to discover pages, check current facts, or find '
            'documentation, then read the pages that matter with web_fetch '
            'and cite the returned url as the source. Write the query as '
            'search keywords, not a sentence; use "site" to stay within one '
            'domain and "freshness" for recent news. Privacy: do NOT put '
            'personal data from records into the query — names of private '
            'individuals, e-mail addresses, phone numbers, VAT numbers, '
            'street addresses — unless the user explicitly asked you to '
            'look that person or number up. AI-agent only.'
        ),
        input_schema={
            'type': 'object',
            'properties': {
                'query': {
                    'type': 'string',
                    'description': 'Search keywords.',
                },
                'count': {
                    'type': 'integer',
                    'description': (
                        f'Number of results (1–{WEB_SEARCH_MAX_RESULTS}). Default 8.'
                    ),
                    'default': 8,
                },
                'freshness': {
                    'type': 'string',
                    'enum': list(FRESHNESS_DAYS),
                    'description': (
                        'Only return pages published within the last day, '
                        'week, month or year.'
                    ),
                },
                'site': {
                    'type': 'string',
                    'description': (
                        'Restrict results to one domain, e.g. "docs.python.org".'
                    ),
                },
            },
            'required': ['query'],
        },
        category='read',
        registry='odoo',
    )
    def _mcp_web_search(
        self,
        query: str,
        count: int = 8,
        freshness: str | None = None,
        site: str | None = None,
    ) -> dict:
        """Search the web through the configured backend, in the company's locale.

        :return: a ``{type, query, backend, results}`` descriptor whose results
            carry ``{url, title, snippet, domain, published, icon}``, or
            ``{query, error}`` when no backend answers
        """
        if (backend := search_backend(self.env)) is None:
            return {'query': query, 'error': 'No web search backend is configured.'}
        request = SearchQuery(
            query=query,
            count=max(1, min(int(count or 8), WEB_SEARCH_MAX_RESULTS)),
            country=self.env.company.country_id.code or '',
            language=self.env.user.lang or '',
            freshness=freshness if freshness in FRESHNESS_DAYS else None,
            site=(site or '').strip() or None,
        )
        try:
            hits = backend.search(request)
        except UserError as exc:
            return {'query': query, 'error': str(exc)}
        icons = self._ai_cache_favicons([(hit.url, hit.icon) for hit in hits])
        return {
            'type': 'web_search',
            'query': query,
            'backend': backend.code,
            'results': [
                {
                    'url': hit.url,
                    'title': hit.title,
                    'snippet': hit.snippet,
                    'domain': (domain := web_domain(hit.url)),
                    'published': hit.published,
                    'icon': icons.get(domain),
                }
                for hit in hits
            ],
        }

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

        :return: a ``{type, url, title, icon, content, content_type, bytes,
            total_chars, offset, next_offset, truncated}`` descriptor, or
            ``{url, error}`` when the fetch fails
        """
        if mode not in ('markdown', 'text', 'html'):
            mode = 'markdown'
        try:
            result = fetch_url(url)
        except (UserError, urllib3.exceptions.HTTPError) as exc:
            return {'url': url, 'error': str(exc)}
        title, content = render_content(result, mode=mode)
        icons = self._ai_cache_favicons([(result.url, page_icon(result))])
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
            'icon': icons.get(web_domain(result.url)),
            'content': window,
            'content_type': result.content_type,
            'bytes': len(result.body),
            'total_chars': total,
            'offset': offset,
            'next_offset': next_offset if truncated else None,
            'truncated': truncated,
        }

    # ----------------------------------------------------------
    # Cron
    # ----------------------------------------------------------

    @api.autovacuum
    def _gc_favicons(self) -> tuple[int, int]:
        """Delete the favicons of the domains nothing has cited for a while.

        Aged out rather than reference counted, so a refused icon is retried.

        :return: how many were deleted, and how many are still due
        """
        cutoff = fields.Datetime.now() - timedelta(days=FAVICON_MAX_AGE_DAYS)
        stale_domain = [
            ('url', '=like', f'{FAVICON_ROUTE}/%'),
            ('res_model', '=', False),
            ('write_date', '<', cutoff),
        ]
        attachments = self.env['ir.attachment'].sudo()
        stale = attachments.search(stale_domain, limit=FAVICON_GC_BATCH)
        count = len(stale)
        stale.unlink()
        if count < FAVICON_GC_BATCH:
            return count, 0
        return count, attachments.search_count(stale_domain)
