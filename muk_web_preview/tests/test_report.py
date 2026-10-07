from __future__ import annotations

import json
from urllib.parse import urlencode

from requests import Response

from odoo.tests import HttpCase, new_test_user
from odoo.tools import mute_logger


class TestReport(HttpCase):
    """Test the inline report route and the report tab setting."""

    @classmethod
    def setUpClass(cls) -> None:
        """Create a partner report, an employee and a partner they cannot read."""
        super().setUpClass()
        cls.env['ir.ui.view'].create(
            {
                'name': 'muk_web_preview.report_partner',
                'type': 'qweb',
                'key': 'muk_web_preview.report_partner',
                'arch': (
                    '<t t-name="muk_web_preview.report_partner">'
                    '<p t-foreach="docs" t-as="doc" t-out="doc.name"/>'
                    '</t>'
                ),
            }
        )
        cls.report = cls.env['ir.actions.report'].create(
            {
                'name': 'Partner Card',
                'model': 'res.partner',
                'report_type': 'qweb-pdf',
                'report_name': 'muk_web_preview.report_partner',
                'print_report_name': "'Card - %s' % object.name",
            }
        )
        cls.user = new_test_user(
            cls.env, login='preview_report', groups='base.group_user'
        )
        cls.partner = cls.env['res.partner'].create({'name': 'Anna Muster'})
        cls.hidden = cls.env['res.partner'].create(
            {
                'name': 'Hidden Partner',
                'company_id': cls.env['res.company'].create({'name': 'Other'}).id,
            }
        )

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    def _preview(self, partner_ids: list[int]) -> Response:
        """Request the inline partner report as the test user."""
        self.authenticate(self.user.login, self.user.login)
        ids = ','.join(map(str, partner_ids))
        data = json.dumps([f'/report/pdf/{self.report.report_name}/{ids}', 'qweb-pdf'])
        return self.url_open(f'/web_preview/report?{urlencode({"data": data})}')

    # ----------------------------------------------------------
    # Tests
    # ----------------------------------------------------------

    def test_preview(self):
        cases = [
            (
                [self.partner.id],
                "inline; filename*=UTF-8''Card%20-%20Anna%20Muster.pdf",
            ),
            (
                [self.partner.id, self.user.partner_id.id],
                "inline; filename*=UTF-8''Partner%20Card.pdf",
            ),
        ]
        for partner_ids, disposition in cases:
            with self.subTest(partner_ids=partner_ids):
                response = self._preview(partner_ids)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.headers['Content-Disposition'], disposition)
                self.assertIn(b'Anna Muster', response.content)

    def test_preview_refused(self):
        with mute_logger('odoo.addons.web.controllers.report'):
            response = self._preview([self.hidden.id])
        self.assertNotIn('Content-Disposition', response.headers)
        self.assertIn(b'odoo.exceptions.AccessError', response.content)
        self.assertNotIn(b'Hidden Partner', response.content)

    def test_session_info(self):
        for enabled in (True, False):
            self.env['ir.config_parameter'].sudo().set_bool(
                'muk_web_preview.report_open', enabled
            )
            self.authenticate(self.user.login, self.user.login)
            session_info = self.make_jsonrpc_request('/web/session/get_session_info')
            self.assertEqual(session_info['preview_report_open'], enabled)
