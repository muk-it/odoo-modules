from odoo.tests import HttpCase, new_test_user
from odoo.tools import BinaryBytes


class TestSessionInfo(HttpCase):
    """Cover the background image flag added to the session info companies."""

    def test_flag_reflects_the_company_image(self):
        company_a = self.env.company
        company_b, company_archived = self.env['res.company'].create(
            [{'name': 'Theme Co B'}, {'name': 'Theme Co Archived'}]
        )
        new_test_user(
            self.env,
            login='theme_session',
            groups='base.group_user',
            company_id=company_a.id,
            company_ids=[(6, 0, (company_a + company_b + company_archived).ids)],
        )
        company_archived.active = False
        company_a.background_image = False
        company_b.background_image = BinaryBytes(b'background')
        self.authenticate('theme_session', 'theme_session')
        info = self.make_jsonrpc_request('/web/session/get_session_info', {})
        allowed = info['user_companies']['allowed_companies']
        self.assertFalse(allowed[str(company_a.id)]['has_background_image'])
        self.assertTrue(allowed[str(company_b.id)]['has_background_image'])
