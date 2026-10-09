from __future__ import annotations

from odoo.tests import HttpCase, no_retry, tagged


@tagged('post_install', '-at_install')
class TestHoot(HttpCase):
    """Run the muk_ai_chatter HOOT JavaScript test suite."""

    # ----------------------------------------------------------
    # Tests
    # ----------------------------------------------------------

    @no_retry
    def test_hoot_muk_ai_chatter(self):
        self.browser_js(
            '/web/tests?headless&loglevel=2&preset=desktop&timeout=15000&tag=muk_ai_chatter',
            '',
            '',
            login='admin',
            timeout=1800,
            success_signal='[HOOT] Test suite succeeded',
            error_checker=lambda message: '[HOOT]' not in message,
        )
