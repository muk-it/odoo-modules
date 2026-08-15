from __future__ import annotations

from datetime import timedelta

from odoo import fields
from odoo.tests import tagged
from odoo.tests.common import HttpCase

from .common import LlmsTxtCommon


@tagged('post_install', '-at_install')
class TestLlmsTxtVisibility(LlmsTxtCommon, HttpCase):
    """Test that access-restricted pages are excluded from the llms routes."""

    # ----------------------------------------------------------
    # Setup
    # ----------------------------------------------------------

    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls.website = cls._setup_llms_website()
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
        cls.unpublished_page = cls._create_page(
            'Llms Draft Page',
            '/llms-visibility-draft',
            'LLMS_SECRET_DRAFT_TEXT',
            is_published=False,
        )
        cls.scheduled_page = cls._create_page(
            'Llms Scheduled Page',
            '/llms-visibility-scheduled',
            'LLMS_SECRET_SCHEDULED_TEXT',
            date_publish=fields.Datetime.now() + timedelta(days=7),
        )
        cls.website._generate_llms_document('llms.txt')
        cls.website._generate_llms_document('llms-full.txt')

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
        self.assertNotIn('/llms-visibility-draft', content)

    def test_llms_full_txt_excludes_gated_page_content(self):
        response = self.url_open('/llms-full.txt')
        self.assertEqual(response.status_code, 200)
        content = response.text
        self.assertIn('/llms-visibility-public', content)
        self.assertIn('LLMS_PUBLIC_MARKER', content)
        for path, marker in (
            ('/llms-visibility-members', 'LLMS_SECRET_MEMBER_TEXT'),
            ('/llms-visibility-password', 'LLMS_SECRET_PASSWORD_TEXT'),
            ('/llms-visibility-group', 'LLMS_SECRET_GROUP_TEXT'),
            ('/llms-visibility-draft', 'LLMS_SECRET_DRAFT_TEXT'),
        ):
            self.assertNotIn(path, content)
            self.assertNotIn(marker, content)

    def test_gated_page_direct_access_is_refused(self):
        self.assertEqual(self.url_open('/llms-visibility-members').status_code, 403)
        self.assertEqual(self.url_open('/llms-visibility-group').status_code, 403)

    def test_gated_pages_are_excluded_from_the_search_domain(self):
        pages = self.env['website.page'].search(self.website._get_llms_page_domain())
        self.assertIn(self.public_page, pages)
        for page in (
            self.connected_page,
            self.password_page,
            self.group_page,
            self.unpublished_page,
        ):
            self.assertNotIn(page, pages)

    def test_scheduled_page_is_excluded_from_the_llms_documents(self):
        self.assertFalse(self.scheduled_page.is_visible)
        self.assertEqual(self.url_open('/llms-visibility-scheduled').status_code, 404)
        self.assertNotIn('/llms-visibility-scheduled', self.url_open('/llms.txt').text)
        content = self.url_open('/llms-full.txt').text
        self.assertNotIn('/llms-visibility-scheduled', content)
        self.assertNotIn('LLMS_SECRET_SCHEDULED_TEXT', content)

    def test_scheduled_page_is_excluded_from_the_search_domain(self):
        pages = self.env['website.page'].search(self.website._get_llms_page_domain())
        self.assertNotIn(self.scheduled_page, pages)
