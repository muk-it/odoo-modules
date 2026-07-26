from __future__ import annotations

from odoo import models


class LlmsTxtCommon:
    """Provide the website fixture and page builder shared by the llms.txt tests."""

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    @classmethod
    def _setup_llms_website(cls, **values) -> models.Model:
        """Return the first website configured for the llms.txt tests."""
        website = cls.env['website'].search([], limit=1)
        website.write(
            {
                'llms_txt_enabled': True,
                'llms_full_txt_enabled': True,
                'llms_content_signal': 'all',
                'llms_include_pages': True,
                'llms_link_headers_enabled': True,
                **values,
            }
        )
        return website

    @classmethod
    def _create_page(cls, name: str, url: str, marker: str, **values) -> models.Model:
        """Create a published website page carrying a unique text marker.

        :param name: the display name of the page
        :param url: the page URL, also used to derive the view key
        :param marker: a unique text marker embedded in the page content
        :return: the created ``website.page`` record
        """
        key = f'muk_website_llms_txt.test{url.replace("-", "_").replace("/", "_")}'
        return cls.env['website.page'].create(
            {
                'name': name,
                'url': url,
                'type': 'qweb',
                'key': key,
                'arch': f'<t t-name="{key}"><div>{marker}</div></t>',
                'website_id': cls.website.id,
                'is_published': True,
                **values,
            }
        )
