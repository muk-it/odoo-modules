from __future__ import annotations

import logging
from collections.abc import Iterator

from odoo import api, fields, models
from odoo.fields import Domain

from odoo.addons.muk_website_llms_txt.tools.constants import (
    LLMS_BATCH_SIZE,
    LLMS_DOCUMENT_PREFIX,
)
from odoo.addons.muk_website_llms_txt.tools.converter import (
    estimate_tokens,
    html_to_markdown,
)

_logger = logging.getLogger(__name__)


class Website(models.Model):
    """Build the llms.txt and llms-full.txt content for the website."""

    _inherit = 'website'

    # ----------------------------------------------------------
    # Fields
    # ----------------------------------------------------------

    llms_txt_enabled = fields.Boolean(
        string='Enable llms.txt',
        default=True,
        help=(
            'Serve a /llms.txt file with an AI-readable index '
            'of your published website content.'
        ),
    )

    llms_full_txt_enabled = fields.Boolean(
        string='Enable llms-full.txt',
        default=True,
        help=(
            'Serve a /llms-full.txt file with the full markdown '
            'content of all published pages.'
        ),
    )

    llms_content_signal = fields.Selection(
        selection=[
            ('all', 'Allow AI training + search + input'),
            ('search_input', 'Allow search + AI input only'),
            ('input_only', 'Allow AI input only'),
            ('none', 'No AI usage permitted'),
        ],
        string='Content Signal Policy',
        default='all',
        help=(
            'Control how AI systems may use your content. '
            'Sent via the Content-Signal HTTP header.'
        ),
    )

    llms_include_pages = fields.Boolean(
        string='Include Pages',
        default=True,
        help='Include published website pages in llms.txt.',
    )

    llms_include_blogs = fields.Boolean(
        string='Include Blog Posts',
        default=True,
        help='Include published blog posts in llms.txt.',
    )

    llms_include_products = fields.Boolean(
        string='Include Products',
        default=True,
        help='Include published products in llms.txt.',
    )

    llms_include_events = fields.Boolean(
        string='Include Events',
        default=True,
        help='Include published events in llms.txt.',
    )

    llms_link_headers_enabled = fields.Boolean(
        string='Agent Discovery Link Headers',
        default=True,
        help=(
            'Advertise machine-readable resources to AI agents and crawlers '
            'by adding RFC 8288 Link response headers to your website pages.'
        ),
    )

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    def _get_llms_documents(self) -> dict[str, tuple[str, str]]:
        """Return the served documents mapped to their setting and builder."""
        return {
            'llms.txt': ('llms_txt_enabled', '_build_llms_txt_content'),
            'llms-full.txt': ('llms_full_txt_enabled', '_build_llms_full_txt_content'),
        }

    def _get_llms_document_fields(self) -> frozenset[str]:
        """Return the fields whose change makes the stored documents stale."""
        return frozenset(
            {
                'name',
                'domain',
                'llms_txt_enabled',
                'llms_full_txt_enabled',
                'llms_include_pages',
                'llms_include_blogs',
                'llms_include_products',
                'llms_include_events',
            }
        )

    def _get_llms_link_header(self, path: str = '') -> str:
        """Return the RFC 8288 Link header advertising discovery resources.

        :param path: the current request path, advertised as the markdown
            alternate of the page when provided
        :return: a comma-joined ``Link`` header value pointing to the
            resources this website currently exposes, or an empty string
            when none are enabled
        """
        links = []
        if path:
            links.append(
                f'<{path}>; rel="alternate"; type="text/markdown"; title="Markdown"'
            )
        if self.llms_txt_enabled:
            links.append(
                '</llms.txt>; rel="describedby"; type="text/plain"; title="LLMs.txt"'
            )
        if self.llms_full_txt_enabled:
            links.append(
                '</llms-full.txt>; rel="describedby"; '
                'type="text/plain"; title="LLMs-full.txt"'
            )
        return ', '.join(links)

    def _get_llms_base_url(self) -> str:
        """Return the website's public base URL without a trailing slash."""
        base_url = self.domain or self.env['ir.config_parameter'].sudo().get_param(
            'web.base.url', ''
        )
        return base_url.rstrip('/')

    def _get_llms_header_lines(self) -> list[str]:
        """Return the markdown header lines for the llms.txt document."""
        return [f'# {self.name or "Odoo Website"}']

    def _is_module_installed(self, module_name: str) -> bool:
        """Return whether the named Odoo module is installed."""
        return module_name in self.env['ir.module.module']._installed()

    def _get_llms_published_domain(self) -> Domain:
        """Return the domain matching the records published on this website."""
        return Domain(
            [
                ('website_published', '=', True),
                ('website_id', 'in', [self.id, False]),
            ]
        )

    def _get_llms_page_domain(self) -> Domain:
        """Return the domain matching the publicly visible website pages.

        Mirrors the gate the framework enforces when serving a page, so
        pages restricted to signed-in users, a password or a group, and
        pages still waiting for their publishing date, are never exposed to
        anonymous requesters through the sudo search.
        """
        return self._get_llms_published_domain() & Domain(
            [
                ('visibility', 'in', (False, '')),
                ('group_ids', '=', False),
                '|',
                ('date_publish', '=', False),
                ('date_publish', '<=', fields.Datetime.now()),
            ]
        )

    def _iter_llms_records(
        self, model: str, domain: Domain, order: str
    ) -> Iterator[models.Model]:
        """Yield every matching record, dropping the ORM cache per batch.

        A document covers the whole published catalog, so the records are
        walked in batches and the cache is released between them. This keeps
        the memory a build needs flat instead of growing with the number of
        published records.
        """
        records = self.env[model].sudo().search(domain, order=order)
        for index in range(0, len(records), LLMS_BATCH_SIZE):
            yield from records[index : index + LLMS_BATCH_SIZE]
            self.env.invalidate_all()

    def _search_llms_document(self, document: str) -> models.Model:
        """Return the attachment storing the given document, if any."""
        return (
            self.env['ir.attachment']
            .sudo()
            .search(
                [
                    ('name', '=', f'{LLMS_DOCUMENT_PREFIX}{document}'),
                    ('res_model', '=', 'website'),
                    ('res_id', '=', self.id),
                ],
                order='id desc',
                limit=1,
            )
        )

    def _generate_llms_document(self, document: str) -> models.Model:
        """Render the given document and replace the stored copy in place.

        The content is rendered before the stored copy is touched, so a run
        that fails or exceeds its time limit leaves the previous document
        serving. Documents are rendered in the website's default language:
        the routes carry no language prefix, so a single canonical copy is
        served whatever language the requester negotiated.

        :param document: the name of the route the document is served on
        :return: the attachment holding the stored document
        """
        website = self.with_context(lang=self.default_lang_id.code)
        content = getattr(website, self._get_llms_documents()[document][1])()
        raw = content.encode()
        _logger.info('Website %s: rendered %s, %s bytes.', self.id, document, len(raw))
        values = {
            'name': f'{LLMS_DOCUMENT_PREFIX}{document}',
            'res_model': 'website',
            'res_id': self.id,
            'type': 'binary',
            'mimetype': 'text/plain',
            'public': True,
            'description': str(estimate_tokens(content)),
            'raw': raw,
        }
        stored = self._search_llms_document(document)
        if stored:
            stored.write(values)
            return stored
        return self.env['ir.attachment'].sudo().create(values)

    def _get_llms_document(self, document: str) -> models.Model:
        """Return the stored document, rendering it on first access.

        The cron keeps the documents up to date; rendering here only covers
        the window between enabling a document and the first cron run.
        """
        return self._search_llms_document(document) or self._generate_llms_document(
            document
        )

    def _get_llms_txt_pages(self, base_url: str) -> list[str]:
        """Return llms.txt index lines for the published website pages."""
        if not self.llms_include_pages:
            return []
        lines = []
        for page in self._iter_llms_records(
            'website.page', self._get_llms_page_domain(), 'url'
        ):
            url = page.url or '/'
            if not url.startswith('http'):
                url = f'{base_url}{url}'
            name = page.name or page.url or 'Untitled'
            lines.append(f'- [{name}]({url})')
        if not lines:
            return []
        return ['', '## Pages', '', *lines]

    def _get_llms_txt_blogs(self, base_url: str) -> list[str]:
        """Return llms.txt index lines for the published blog posts."""
        if not self.llms_include_blogs or not self._is_module_installed('website_blog'):
            return []
        lines = []
        for post in self._iter_llms_records(
            'blog.post', self._get_llms_published_domain(), 'published_date desc'
        ):
            url = f'{base_url}{post.website_url or "/"}'
            name = post.name or 'Untitled'
            if post.subtitle:
                lines.append(f'- [{name}]({url}): {post.subtitle}')
            else:
                lines.append(f'- [{name}]({url})')
        if not lines:
            return []
        return ['', '## Blog Posts', '', *lines]

    def _get_llms_txt_products(self, base_url: str) -> list[str]:
        """Return llms.txt index lines for the published products."""
        if not self.llms_include_products or not self._is_module_installed(
            'website_sale'
        ):
            return []
        lines = []
        for product in self._iter_llms_records(
            'product.template', self._get_llms_published_domain(), 'name'
        ):
            url = f'{base_url}{product.website_url or "/"}'
            name = product.name or 'Untitled'
            desc = product.description_sale
            if desc:
                desc = desc.strip().replace('\n', ' ')[:200]
                lines.append(f'- [{name}]({url}): {desc}')
            else:
                lines.append(f'- [{name}]({url})')
        if not lines:
            return []
        return ['', '## Products', '', *lines]

    def _get_llms_txt_events(self, base_url: str) -> list[str]:
        """Return llms.txt index lines for the published events."""
        if not self.llms_include_events or not self._is_module_installed(
            'website_event'
        ):
            return []
        lines = []
        for event in self._iter_llms_records(
            'event.event', self._get_llms_published_domain(), 'date_begin'
        ):
            url = f'{base_url}{event.website_url or "/"}'
            name = event.name or 'Untitled'
            lines.append(f'- [{name}]({url})')
        if not lines:
            return []
        return ['', '## Events', '', *lines]

    def _build_llms_txt_content(self) -> str:
        """Assemble the full llms.txt index document for this website."""
        base_url = self._get_llms_base_url()
        lines = self._get_llms_header_lines()
        lines += self._get_llms_txt_pages(base_url)
        lines += self._get_llms_txt_blogs(base_url)
        lines += self._get_llms_txt_products(base_url)
        lines += self._get_llms_txt_events(base_url)
        lines.append('')
        return '\n'.join(lines)

    def _format_llms_full_entry(
        self, name: str, url: str, content: str = ''
    ) -> list[str]:
        """Return the markdown lines for one llms-full.txt content entry."""
        entry = ['', '---', '', f'## {name}', '', f'URL: {url}', '']
        if content:
            entry.append(content)
        return entry

    def _get_llms_full_pages(self, base_url: str) -> list[str]:
        """Return llms-full.txt entries with the markdown of each page."""
        if not self.llms_include_pages:
            return []
        parts = []
        for page in self._iter_llms_records(
            'website.page', self._get_llms_page_domain(), 'url'
        ):
            url = page.url or '/'
            if not url.startswith('http'):
                url = f'{base_url}{url}'
            name = page.name or page.url or 'Untitled'
            content = ''
            arch = page.arch_db or ''
            if arch:
                content = html_to_markdown(arch, base_url=base_url) or ''
            parts += self._format_llms_full_entry(name, url, content)
        return parts

    def _get_llms_full_blogs(self, base_url: str) -> list[str]:
        """Return llms-full.txt entries with the markdown of each blog post."""
        if not self.llms_include_blogs or not self._is_module_installed('website_blog'):
            return []
        parts = []
        for post in self._iter_llms_records(
            'blog.post', self._get_llms_published_domain(), 'published_date desc'
        ):
            url = f'{base_url}{post.website_url or "/"}'
            name = post.name or 'Untitled'
            content = ''
            content_html = post.content or ''
            if content_html:
                content = html_to_markdown(content_html, base_url=base_url) or ''
            parts += self._format_llms_full_entry(name, url, content)
        return parts

    def _get_llms_full_products(self, base_url: str) -> list[str]:
        """Return llms-full.txt entries with the markdown of each product."""
        if not self.llms_include_products or not self._is_module_installed(
            'website_sale'
        ):
            return []
        parts = []
        for product in self._iter_llms_records(
            'product.template', self._get_llms_published_domain(), 'name'
        ):
            url = f'{base_url}{product.website_url or "/"}'
            name = product.name or 'Untitled'
            entry = ['', '---', '', f'## {name}', '', f'URL: {url}']
            if product.list_price:
                entry.append(f'Price: {product.list_price}')
            entry.append('')
            desc = product.description_sale or ''
            if desc:
                entry.append(desc.strip())
            website_desc = product.website_description or ''
            if website_desc:
                content = html_to_markdown(website_desc, base_url=base_url)
                if content:
                    entry.append('')
                    entry.append(content)
            parts += entry
        return parts

    def _build_llms_full_txt_content(self) -> str:
        """Assemble the full llms-full.txt markdown dump for this website."""
        base_url = self._get_llms_base_url()
        parts = self._get_llms_header_lines()
        parts += self._get_llms_full_pages(base_url)
        parts += self._get_llms_full_blogs(base_url)
        parts += self._get_llms_full_products(base_url)
        parts.append('')
        return '\n'.join(parts)

    # ----------------------------------------------------------
    # ORM
    # ----------------------------------------------------------

    def write(self, vals: dict) -> bool:
        """Schedule a rebuild when the llms.txt configuration changes.

        The stored documents keep serving until the cron has rebuilt them,
        so saving the settings of a large catalog never makes a visitor wait
        for a fresh render.
        """
        result = super().write(vals)
        if not self._get_llms_document_fields().isdisjoint(vals):
            cron = self.env.ref(
                'muk_website_llms_txt.ir_cron_generate_llms_documents',
                raise_if_not_found=False,
            )
            if cron:
                cron.sudo()._trigger()
        return result

    # ----------------------------------------------------------
    # Cron
    # ----------------------------------------------------------

    @api.model
    def _cron_generate_llms_documents(self) -> None:
        """Rebuild the stored llms.txt documents of every website.

        Each document is committed on its own so that a run cut short by
        ``limit_time_real_cron`` keeps the documents it already rebuilt.
        """
        for website in self.search([]):
            documents = website._get_llms_documents()
            for document, (enabled_field, _builder) in documents.items():
                if website[enabled_field]:
                    website._generate_llms_document(document)
                else:
                    website._search_llms_document(document).unlink()
                self.env.cr.commit()
