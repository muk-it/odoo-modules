from __future__ import annotations

import odoo.tests
from odoo.tests.common import tagged


@tagged('post_install', '-at_install')
class TestHoot(odoo.tests.HttpCase):
    """Run the addon HOOT test suite in a headless browser."""

    # ----------------------------------------------------------
    # Tests
    # ----------------------------------------------------------

    @odoo.tests.no_retry
    def test_hoot_muk_web_appsbar(self):
        self.browser_js(
            '/web/tests?headless&loglevel=2&preset=desktop&timeout=15000&tag=muk_web_appsbar',
            '',
            '',
            login='admin',
            timeout=1800,
            success_signal='[HOOT] Test suite succeeded',
            error_checker=lambda message: '[HOOT]' not in message,
        )
