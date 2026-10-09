from __future__ import annotations

from odoo.tests import HttpCase, tagged

from odoo.addons.web.tests.test_js import qunit_error_checker


@tagged('post_install', '-at_install')
class TestQUnit(HttpCase):
    """Run the muk_ai_chatter QUnit JavaScript test suite."""

    # ----------------------------------------------------------
    # Tests
    # ----------------------------------------------------------

    def test_qunit_muk_ai_chatter(self):
        self.browser_js(
            '/web/tests?filter=muk_ai_chatter',
            '',
            '',
            login='admin',
            timeout=1800,
            error_checker=qunit_error_checker,
        )
