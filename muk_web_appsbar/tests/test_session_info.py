from odoo.tests import HttpCase, new_test_user
from odoo.tools import BinaryBytes


class TestSessionInfo(HttpCase):
    """Cover the appsbar image flag added to the session info companies."""

    # ----------------------------------------------------------
    # Tests
    # ----------------------------------------------------------

    def test_flag_reflects_company_image(self):
        company_a = self.env.company
        company_b = self.env['res.company'].create({'name': 'Appsbar Co B'})
        company_a.appbar_image = False
        company_b.appbar_image = BinaryBytes(b'not-really-a-png')
        new_test_user(
            self.env,
            login='appsbar_session',
            password='appsbar_session',
            groups='base.group_user',
            company_id=company_a.id,
            company_ids=[(6, 0, [company_a.id, company_b.id])],
        )
        self.authenticate('appsbar_session', 'appsbar_session')
        info = self.make_jsonrpc_request(
            '/web/session/get_session_info', {}, timeout=120
        )
        allowed = info['user_companies']['allowed_companies']
        self.assertFalse(allowed[str(company_a.id)]['has_appsbar_image'])
        self.assertTrue(allowed[str(company_b.id)]['has_appsbar_image'])
