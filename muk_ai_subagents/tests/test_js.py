from __future__ import annotations

from odoo.tests import HttpCase, no_retry, tagged


@tagged('hoot')
class TestHoot(HttpCase):
    """Run the muk_ai_subagents HOOT JavaScript test suite."""

    # ----------------------------------------------------------
    # Tests
    # ----------------------------------------------------------

    @no_retry
    def test_hoot_muk_ai_subagents(self):
        for preset in ('desktop', 'mobile'):
            with self.subTest(preset):
                self.browser_js(
                    f'/web/tests?headless&loglevel=2&preset={preset}'
                    '&timeout=15000&tag=muk_ai_subagents',
                    '',
                    '',
                    login='admin',
                    timeout=1800,
                    success_signal='[HOOT] Test suite succeeded',
                    error_checker=lambda message: '[HOOT]' not in message,
                )
