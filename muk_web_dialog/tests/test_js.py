from __future__ import annotations

from odoo.tests import HttpCase, no_retry, tagged


class HootCase(HttpCase):
    """Run the addon HOOT test suite in a headless browser."""

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    def _run_hoot(self, preset: str) -> None:
        """Run the addon HOOT tests with the given device preset."""
        self.browser_js(
            f'/web/tests?headless&loglevel=2&preset={preset}&timeout=15000'
            '&tag=muk_web_dialog',
            '',
            '',
            login='admin',
            timeout=1800,
            success_signal='[HOOT] Test suite succeeded',
            error_checker=lambda message: '[HOOT]' not in message,
        )


@tagged('hoot')
class TestHoot(HootCase):
    """Run the addon HOOT test suite in a headless desktop browser."""

    # ----------------------------------------------------------
    # Tests
    # ----------------------------------------------------------

    @no_retry
    def test_hoot_desktop(self):
        self._run_hoot('desktop')


@tagged('hoot')
class TestHootMobile(HootCase):
    """Run the addon HOOT test suite in a headless mobile browser."""

    browser_size = '375x667'
    touch_enabled = True

    # ----------------------------------------------------------
    # Tests
    # ----------------------------------------------------------

    @no_retry
    def test_hoot_mobile(self):
        self._run_hoot('mobile')
