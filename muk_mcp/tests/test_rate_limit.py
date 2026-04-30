import time
import threading

from odoo.tests import common, tagged

from odoo.addons.muk_mcp.tools.rate_limit import RateLimiter

@tagged('post_install', '-at_install')
class RateLimiterTestCase(common.TransactionCase):

    # ----------------------------------------------------------
    # Setup
    # ----------------------------------------------------------

    def setUp(self):
        super().setUp()
        self.limiter = RateLimiter()

    # ----------------------------------------------------------
    # Tests
    # ----------------------------------------------------------

    def test_disabled_when_zero(self):
        for _ in range(100):
            self.assertTrue(self.limiter.check('key', 0, 60))

    def test_allows_within_limit(self):
        for _ in range(5):
            self.assertTrue(self.limiter.check('key', 5, 60))

    def test_blocks_over_limit(self):
        for _ in range(3):
            self.limiter.check('key', 3, 60)
        self.assertFalse(self.limiter.check('key', 3, 60))

    def test_separate_keys(self):
        for _ in range(3):
            self.limiter.check('key_a', 3, 60)
        self.assertFalse(self.limiter.check('key_a', 3, 60))
        self.assertTrue(self.limiter.check('key_b', 3, 60))

    def test_window_expiry(self):
        for _ in range(3):
            self.limiter.check('key', 3, 0.05)
        self.assertFalse(self.limiter.check('key', 3, 0.05))
        time.sleep(0.06)
        self.assertTrue(self.limiter.check('key', 3, 0.05))

    def test_cleanup_removes_stale_keys(self):
        self.limiter.check('old', 10, 60)
        self.limiter.check('recent', 10, 60)
        now = time.monotonic()
        self.limiter._windows['old'] = [now - 7200]
        self.limiter._cleanup_stale(now, max_age=3600)
        self.assertNotIn('old', self.limiter._windows)
        self.assertIn('recent', self.limiter._windows)

    def test_cleanup_removes_empty_lists(self):
        self.limiter._windows['empty'] = []
        self.limiter._cleanup_stale(time.monotonic(), max_age=3600)
        self.assertNotIn('empty', self.limiter._windows)

    def test_thread_safety(self):
        results = []

        def hammer():
            for _ in range(50):
                results.append(self.limiter.check('shared', 200, 60))

        threads = [threading.Thread(target=hammer) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        allowed = sum(1 for r in results if r)
        self.assertEqual(allowed, 200)
        self.assertEqual(len(results), 200)
