from __future__ import annotations

from odoo.tests import HttpCase, tagged

from odoo.addons.web.tests.test_js import qunit_error_checker


@tagged('post_install', '-at_install')
class TestQUnit(HttpCase):
    """Run the muk_mail_route QUnit JavaScript test suite."""

    # ----------------------------------------------------------
    # Tests
    # ----------------------------------------------------------

    def test_qunit_muk_mail_route(self):
        self.browser_js(
            '/web/tests?filter=muk_mail_route',
            '',
            '',
            login='admin',
            timeout=1800,
            error_checker=qunit_error_checker,
        )
