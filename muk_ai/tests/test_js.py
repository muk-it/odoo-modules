import odoo.tests

from odoo.tests.common import new_test_user, tagged


@tagged('post_install', '-at_install')
class TestHoot(odoo.tests.HttpCase):

    # ----------------------------------------------------------
    # Setup
    # ----------------------------------------------------------

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # group_system is required on Odoo 18: the Hoot test runner resolves a
        # non-default addon's dependencies via ir.module.module.dependency
        # .all_dependencies(), which is restricted to Settings access on 18
        # (readable by all users on 19). The suite itself uses a mock server,
        # so the elevated group does not affect the component tests.
        cls.hoot_user = new_test_user(
            cls.env,
            login='hoot_muk_ai',
            password='hoot_muk_ai',
            groups='base.group_user,base.group_system',
            context={
                'mail_create_nosubscribe': True,
                'mail_notrack': True,
                'no_reset_password': True,
            },
        )

    # ----------------------------------------------------------
    # Tests
    # ----------------------------------------------------------

    @odoo.tests.no_retry
    def test_hoot_muk_ai(self):
        self.browser_js(
            '/web/tests?headless&loglevel=2&preset=desktop&timeout=15000&tag=muk_ai',
            '',
            '',
            login=self.hoot_user.login,
            timeout=1800,
            success_signal='[HOOT] Test suite succeeded',
            error_checker=lambda message: '[HOOT]' not in message,
        )
