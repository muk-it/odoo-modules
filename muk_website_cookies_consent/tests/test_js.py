from odoo.tests import HttpCase, no_retry, tagged


@tagged('hoot')
class TestHoot(HttpCase):
    """Run the front-end Hoot JavaScript unit tests."""

    # ----------------------------------------------------------
    # Tests
    # ----------------------------------------------------------

    @no_retry
    def test_hoot_muk_website_cookies_consent(self):
        self.browser_js(
            '/web/tests?headless&loglevel=2&preset=desktop&timeout=15000'
            '&tag=muk_website_cookies_consent',
            '',
            '',
            login='admin',
            timeout=1800,
            success_signal='[HOOT] Test suite succeeded',
            error_checker=lambda message: '[HOOT]' not in message,
        )
