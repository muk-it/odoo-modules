import collections
import time
import threading


class RateLimiter:

    def __init__(self):
        self._windows = {}
        self._check_count = 0
        self._lock = threading.Lock()
        self._last_cleanup = time.monotonic()

    def check(self, key, max_requests, window_seconds):
        if max_requests <= 0:
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
                    maxlen=max_requests + 1
                )
                self._windows[key] = timestamps
            while timestamps and timestamps[0] <= cutoff:
                timestamps.popleft()
            if len(timestamps) >= max_requests:
                return False
            timestamps.append(now)
            return True

    def _cleanup_stale(self, now, max_age=3600):
        cutoff = now - max_age
        stale_keys = [
            k for k, v in self._windows.items()
            if not v or v[-1] < cutoff
        ]
        for key in stale_keys:
            del self._windows[key]


rate_limiter = RateLimiter()
