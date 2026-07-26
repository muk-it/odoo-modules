from __future__ import annotations

from unittest.mock import patch

from odoo.tests import common

from odoo.addons.muk_mcp.tools.logger import LoggerProxy


class TestLoggerProxy(common.TransactionCase):
    """Cover the sandbox logger proxy exposed to database tool code."""

    # ----------------------------------------------------------
    # Setup
    # ----------------------------------------------------------

    def setUp(self) -> None:
        super().setUp()
        self.proxy = LoggerProxy('muk_mcp.tests.logger_proxy')

    # ----------------------------------------------------------
    # Tests
    # ----------------------------------------------------------

    def test_info_delegates(self):
        with patch.object(self.proxy._logger, 'info') as mocked:
            self.proxy.info('hello %s', 'world')
        mocked.assert_called_once_with('hello %s', 'world')

    def test_warning_delegates(self):
        with patch.object(self.proxy._logger, 'warning') as mocked:
            self.proxy.warning('careful')
        mocked.assert_called_once_with('careful')

    def test_error_delegates_without_exc_info(self):
        with patch.object(self.proxy._logger, 'error') as mocked:
            self.proxy.error('broken %d', 7)
        mocked.assert_called_once_with('broken %d', 7)

    def test_exception_logs_at_error_level_with_exc_info(self):
        with patch.object(self.proxy._logger, 'error') as mocked:
            self.proxy.exception('boom %s', 'now')
        mocked.assert_called_once_with('boom %s', 'now', exc_info=True)

    def test_exception_keeps_an_explicit_exc_info(self):
        with patch.object(self.proxy._logger, 'error') as mocked:
            self.proxy.exception('boom', exc_info=False)
        mocked.assert_called_once_with('boom', exc_info=False)
