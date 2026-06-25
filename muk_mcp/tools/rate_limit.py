from __future__ import annotations

import collections
import threading
import time
from typing import Any


class RateLimiter:
    """In-memory sliding-window rate limiter shared across requests."""

    def __init__(self) -> None:
        """Initialise the empty per-key request-timestamp buckets."""
        self._windows = {}
        self._check_count = 0
        self._lock = threading.Lock()
        self._last_cleanup = time.monotonic()

    def check(
        self,
        key: Any,
        max_requests: int,
        window_seconds: float,
        count: int = 1,
    ) -> bool:
        """Record ``count`` requests for ``key`` and report whether they fit the window.

        :return: ``True`` if the requests stay within ``max_requests`` over the
            trailing ``window_seconds``; ``False`` if they would exceed the limit,
            in which case no timestamps are recorded.
        """
        if max_requests <= 0:
            return True
        if count <= 0:
            return True
        now = time.monotonic()
        cutoff = now - window_seconds
        with self._lock:
            self._check_count += 1
            if now - self._last_cleanup > 300:
                self._cleanup_stale(now)
                self._last_cleanup = now
            timestamps = self._windows.get(key)
            if timestamps is None:
                timestamps = collections.deque(
                    maxlen=max_requests + count,
                )
                self._windows[key] = timestamps
            while timestamps and timestamps[0] <= cutoff:
                timestamps.popleft()
            if len(timestamps) + count > max_requests:
                return False
            timestamps.extend([now] * count)
            return True

    def _cleanup_stale(self, now: float, max_age: float = 3600) -> None:
        """Drop tracking state for keys with no activity within ``max_age`` seconds."""
        cutoff = now - max_age
        stale_keys = [k for k, v in self._windows.items() if not v or v[-1] < cutoff]
        for key in stale_keys:
            del self._windows[key]


rate_limiter = RateLimiter()
