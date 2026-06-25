from __future__ import annotations

import logging
from typing import Any


class LoggerProxy:
    """Thin wrapper over a named :mod:`logging` logger used throughout MCP."""

    def __init__(self, name: str) -> None:
        """Wrap the named stdlib logger."""
        self._logger = logging.getLogger(name)

    def info(self, message: str, *args: Any, **kwargs: Any) -> None:
        """Log an info-level message through the wrapped logger."""
        self._logger.info(message, *args, **kwargs)

    def warning(self, message: str, *args: Any, **kwargs: Any) -> None:
        """Log a warning-level message through the wrapped logger."""
        self._logger.warning(message, *args, **kwargs)

    def error(self, message: str, *args: Any, **kwargs: Any) -> None:
        """Log an error-level message through the wrapped logger."""
        self._logger.error(message, *args, **kwargs)

    def exception(self, message: str, *args: Any, **kwargs: Any) -> None:
        """Log an error-level message with the active traceback (exc_info)."""
        kwargs.setdefault('exc_info', True)
        self._logger.error(message, *args, **kwargs)
