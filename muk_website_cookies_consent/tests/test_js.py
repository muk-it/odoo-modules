from __future__ import annotations

import odoo.tests
from odoo.tests.common import tagged

from odoo.addons.web.tests.test_js import qunit_error_checker


@tagged('post_install', '-at_install')
class TestQUnit(odoo.tests.HttpCase):
    """Run the front-end QUnit JavaScript unit tests."""

    # ----------------------------------------------------------
    # Tests
    # ----------------------------------------------------------

    def test_qunit_muk_website_cookies_consent(self):
        self.browser_js(
            '/web/tests?filter=muk_website_cookies_consent',
            '',
            '',
            login='admin',
            timeout=1800,
            error_checker=qunit_error_checker,
        )
