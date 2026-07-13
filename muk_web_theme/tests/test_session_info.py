from __future__ import annotations

from odoo.tests import tagged
from odoo.tests.common import HttpCase


@tagged('post_install', '-at_install')
class TestSessionInfo(HttpCase):
    """Test that an archived allowed company does not break session_info."""

    # ----------------------------------------------------------
    # Tests
    # ----------------------------------------------------------

    def test_session_info_skips_archived_company(self):
        company_a = self.env.company
        company_b = self.env['res.company'].create({'name': 'Archived Co'})
        user = self.env['res.users'].create(
            {
                'name': 'Multi Co User',
                'login': 'muk_web_theme_multi_co',
                'company_id': company_a.id,
                'company_ids': [(6, 0, [company_a.id, company_b.id])],
                'group_ids': [(6, 0, [self.env.ref('base.group_user').id])],
            }
        )
        company_b.active = False
        self.authenticate('muk_web_theme_multi_co', 'muk_web_theme_multi_co')
        info = self.make_jsonrpc_request('/web/session/get_session_info', {})
        allowed = info['user_companies']['allowed_companies']
        self.assertIn(company_a.id, allowed)
        self.assertIn('has_background_image', allowed[company_a.id])
        self.assertNotIn(company_b.id, allowed)
        self.assertEqual(user.company_id, company_a)
