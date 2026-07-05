from __future__ import annotations

from odoo import models
from odoo.tests import tagged
from odoo.tests.common import HttpCase


@tagged('post_install', '-at_install')
class TestLlmsTxtVisibility(HttpCase):
    """Test that access-restricted pages are excluded from the llms routes."""

    # ----------------------------------------------------------
    # Setup
    # ----------------------------------------------------------

    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls.website = cls.env['website'].search([], limit=1)
        cls.website.write(
            {
                'llms_txt_enabled': True,
                'llms_full_txt_enabled': True,
                'llms_include_pages': True,
            }
        )
        cls.public_page = cls._create_page(
            'Llms Public Page',
            '/llms-visibility-public',
            'LLMS_PUBLIC_MARKER',
        )
        cls.connected_page = cls._create_page(
            'Llms Members Page',
            '/llms-visibility-members',
            'LLMS_SECRET_MEMBER_TEXT',
            visibility='connected',
        )
        cls.password_page = cls._create_page(
            'Llms Password Page',
            '/llms-visibility-password',
            'LLMS_SECRET_PASSWORD_TEXT',
            visibility='password',
        )
        cls.group_page = cls._create_page(
            'Llms Group Page',
            '/llms-visibility-group',
            'LLMS_SECRET_GROUP_TEXT',
            visibility='restricted_group',
            group_ids=[(6, 0, [cls.env.ref('base.group_system').id])],
        )

    @classmethod
    def _create_page(
        cls,
        name: str,
        url: str,
        marker: str,
        visibility: str = '',
        group_ids: list | None = None,
    ) -> models.Model:
        """Create a published website page with the given view visibility.

        :param name: the display name of the page
        :param url: the page URL, used as the view key suffix as well
        :param marker: a unique text marker embedded in the page content
        :param visibility: the backing view visibility gate
        :param group_ids: the restricted group commands for the backing view
        :return: the created ``website.page`` record
        """
        key = f'muk_website_llms_txt.test{url.replace("-", "_").replace("/", "_")}'
        values = {
            'name': name,
            'url': url,
            'type': 'qweb',
            'key': key,
            'arch': f'<t t-name="{key}"><div>{marker}</div></t>',
            'website_id': cls.website.id,
            'is_published': True,
            'visibility': visibility,
        }
        if group_ids:
            values['group_ids'] = group_ids
        return cls.env['website.page'].create(values)

    # ----------------------------------------------------------
    # Tests
    # ----------------------------------------------------------

    def test_llms_txt_excludes_gated_pages(self):
        response = self.url_open('/llms.txt')
        self.assertEqual(response.status_code, 200)
        content = response.text
        self.assertIn('/llms-visibility-public', content)
        self.assertNotIn('/llms-visibility-members', content)
        self.assertNotIn('/llms-visibility-password', content)
        self.assertNotIn('/llms-visibility-group', content)

    def test_llms_full_txt_excludes_gated_pages(self):
        response = self.url_open('/llms-full.txt')
        self.assertEqual(response.status_code, 200)
        content = response.text
        self.assertIn('/llms-visibility-public', content)
        self.assertIn('LLMS_PUBLIC_MARKER', content)
        self.assertNotIn('/llms-visibility-members', content)
        self.assertNotIn('LLMS_SECRET_MEMBER_TEXT', content)
        self.assertNotIn('/llms-visibility-password', content)
        self.assertNotIn('LLMS_SECRET_PASSWORD_TEXT', content)
        self.assertNotIn('/llms-visibility-group', content)
        self.assertNotIn('LLMS_SECRET_GROUP_TEXT', content)

    def test_gated_page_direct_access_forbidden(self):
        response = self.url_open('/llms-visibility-members')
        self.assertEqual(response.status_code, 403)
