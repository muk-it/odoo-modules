from odoo.tests import HttpCase, tagged


@tagged('hoot')
class TestHoot(HttpCase):
    """Run the muk_web_preview HOOT JavaScript test suite."""

    def test_hoot(self):
        self.browser_js(
            '/web/tests?headless&loglevel=2&preset=desktop&timeout=15000&tag=muk_web_preview',
            '',
            '',
            login='admin',
            timeout=1800,
            success_signal='[HOOT] Test suite succeeded',
            error_checker=lambda message: '[HOOT]' not in message,
        )
