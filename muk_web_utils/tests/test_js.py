from __future__ import annotations

from odoo.tests import HttpCase, no_retry, tagged


@tagged('hoot')
class TestHoot(HttpCase):
    """Run the addon HOOT test suite in a headless browser."""

    # ----------------------------------------------------------
    # Tests
    # ----------------------------------------------------------

    @no_retry
    def test_hoot_muk_web_utils(self):
        self.browser_js(
            '/web/tests?headless&loglevel=2&preset=desktop&timeout=15000&tag=muk_web_utils',
            '',
            '',
            login='admin',
            timeout=1800,
            success_signal='[HOOT] Test suite succeeded',
            error_checker=lambda message: '[HOOT]' not in message,
        )
