import logging

from odoo import fields, models

_logger = logging.getLogger(__name__)


class Website(models.Model):

    _inherit = 'website'

    # ----------------------------------------------------------
    # Fields
    # ----------------------------------------------------------

    llms_txt_enabled = fields.Boolean(
        string="Enable llms.txt",
        default=True,
        help=(
            "Serve a /llms.txt file with an AI-readable index "
            "of your published website content."
        )
    )

    llms_full_txt_enabled = fields.Boolean(
        string="Enable llms-full.txt",
        default=True,
        help=(
            "Serve a /llms-full.txt file with the full markdown "
            "content of all published pages."
        )
    )

    llms_content_signal = fields.Selection(
        selection=[
            ('all', "Allow AI training + search + input"),
            ('search_input', "Allow search + AI input only"),
            ('input_only', "Allow AI input only"),
            ('none', "No AI usage permitted"),
        ],
        string="Content Signal Policy",
        default='all',
        help=(
            "Control how AI systems may use your content. "
            "Sent via the Content-Signal HTTP header."
        )
    )

    llms_include_pages = fields.Boolean(
        string="Include Pages",
        default=True,
        help="Include published website pages in llms.txt."
    )

    llms_include_blogs = fields.Boolean(
        string="Include Blog Posts",
        default=True,
        help="Include published blog posts in llms.txt."
    )

    llms_include_products = fields.Boolean(
        string="Include Products",
        default=True,
        help="Include published products in llms.txt."
    )

    llms_include_events = fields.Boolean(
        string="Include Events",
        default=True,
        help="Include published events in llms.txt."
    )

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    def _get_llms_base_url(self):
        self.ensure_one()
        base_url = (
            self.domain
            or self.env['ir.config_parameter']
            .sudo()
            .get_param('web.base.url', '')
        )
        return base_url.rstrip('/')

    def _get_llms_header_lines(self):
        self.ensure_one()
        return [f'# {self.name or "Odoo Website"}']

    def _is_module_installed(self, module_name):
        return bool(self.env['ir.module.module'].sudo().search(
            [('name', '=', module_name), ('state', '=', 'installed')],
            limit=1
        ))

    def _get_llms_txt_pages(self, base_url):
        if not self.llms_include_pages:
            return []
        pages = self.env['website.page'].sudo().search(
            [
                ('website_published', '=', True),
                ('website_id', 'in', [self.id, False]),
            ],
            order='url'
        )
        if not pages:
            return []
        lines = ['', '## Pages', '']
        for page in pages:
            url = page.url or '/'
            if not url.startswith('http'):
                url = f'{base_url}{url}'
            name = page.name or page.url or 'Untitled'
            lines.append(f'- [{name}]({url})')
        return lines

    def _get_llms_txt_blogs(self, base_url):
        if (
            not self.llms_include_blogs or
            not self._is_module_installed('website_blog')
        ):
            return []
        blog_posts = self.env['blog.post'].sudo().search(
            [
                ('website_published', '=', True),
                ('website_id', 'in', [self.id, False]),
            ],
            order='published_date desc'
        )
        if not blog_posts:
            return []
        lines = ['', '## Blog Posts', '']
        for post in blog_posts:
            url = f'{base_url}{post.website_url or "/"}'
            name = post.name or 'Untitled'
            if post.subtitle:
                lines.append(f'- [{name}]({url}): {post.subtitle}')
            else:
                lines.append(f'- [{name}]({url})')
        return lines

    def _get_llms_txt_products(self, base_url):
        if (
            not self.llms_include_products or
            not self._is_module_installed('website_sale')
        ):
            return []
        products = self.env['product.template'].sudo().search(
            [
                ('website_published', '=', True),
                ('website_id', 'in', [self.id, False]),
            ],
            order='name'
        )
        if not products:
            return []
        lines = ['', '## Products', '']
        for product in products:
            url = f'{base_url}{product.website_url or "/"}'
            name = product.name or 'Untitled'
            desc = product.description_sale
            if desc:
                desc = desc.strip().replace('\n', ' ')[:200]
                lines.append(f'- [{name}]({url}): {desc}')
            else:
                lines.append(f'- [{name}]({url})')
        return lines

    def _get_llms_txt_events(self, base_url):
        if (
            not self.llms_include_events or
            not self._is_module_installed('website_event')
        ):
            return []
        events = self.env['event.event'].sudo().search(
            [
                ('website_published', '=', True),
                ('website_id', 'in', [self.id, False]),
            ],
            order='date_begin'
        )
        if not events:
            return []
        lines = ['', '## Events', '']
        for event in events:
            url = f'{base_url}{event.website_url or "/"}'
            name = event.name or 'Untitled'
            lines.append(f'- [{name}]({url})')
        return lines

    def _get_llms_txt_content(self):
        self.ensure_one()
        base_url = self._get_llms_base_url()
        lines = self._get_llms_header_lines()
        lines += self._get_llms_txt_pages(base_url)
        lines += self._get_llms_txt_blogs(base_url)
        lines += self._get_llms_txt_products(base_url)
        lines += self._get_llms_txt_events(base_url)
        lines.append('')
        return '\n'.join(lines)

    def _format_llms_full_entry(self, name, url, content=''):
        entry = ['', '---', '', f'## {name}', '', f'URL: {url}', '']
        if content:
            entry.append(content)
        return entry

    def _get_llms_full_pages(self, base_url, html_to_markdown):
        if not self.llms_include_pages:
            return []
        pages = self.env['website.page'].sudo().search(
            [
                ('website_published', '=', True),
                ('website_id', 'in', [self.id, False]),
            ],
            order='url'
        )
        parts = []
        for page in pages:
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

    def _get_llms_full_blogs(self, base_url, html_to_markdown):
        if (
            not self.llms_include_blogs or
            not self._is_module_installed('website_blog')
        ):
            return []
        blog_posts = self.env['blog.post'].sudo().search(
            [
                ('website_published', '=', True),
                ('website_id', 'in', [self.id, False]),
            ],
            order='published_date desc'
        )
        parts = []
        for post in blog_posts:
            url = f'{base_url}{post.website_url or "/"}'
            name = post.name or 'Untitled'
            content = ''
            content_html = post.content or ''
            if content_html:
                content = html_to_markdown(
                    content_html, base_url=base_url
                ) or ''
            parts += self._format_llms_full_entry(name, url, content)
        return parts

    def _get_llms_full_products(self, base_url, html_to_markdown):
        if (
            not self.llms_include_products or
            not self._is_module_installed('website_sale')
        ):
            return []
        products = self.env['product.template'].sudo().search(
            [
                ('website_published', '=', True),
                ('website_id', 'in', [self.id, False]),
            ],
            order='name'
        )
        parts = []
        for product in products:
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
                content = html_to_markdown(
                    website_desc, base_url=base_url
                )
                if content:
                    entry.append('')
                    entry.append(content)
            parts += entry
        return parts

    def _get_llms_full_txt_content(self):
        self.ensure_one()
        from odoo.addons.muk_website_llms_txt.tools.converter import (
            html_to_markdown,
        )
        base_url = self._get_llms_base_url()
        parts = self._get_llms_header_lines()
        parts += self._get_llms_full_pages(base_url, html_to_markdown)
        parts += self._get_llms_full_blogs(base_url, html_to_markdown)
        parts += self._get_llms_full_products(base_url, html_to_markdown)
        parts.append('')
        return '\n'.join(parts)
