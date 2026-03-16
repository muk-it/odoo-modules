import time
import threading

class RateLimiter:

    def __init__(self):
        self._lock = threading.Lock()
        self._windows = {}
        self._check_count = 0

    def check(self, key, max_requests, window_seconds):
        if max_requests <= 0:
            return True
        now = time.monotonic()
        cutoff = now - window_seconds
        with self._lock:
            self._check_count += 1
            if self._check_count % 1000 == 0:
                self._cleanup_stale(now)
            timestamps = self._windows.get(key, [])
            timestamps = [t for t in timestamps if t > cutoff]
            if len(timestamps) >= max_requests:
                self._windows[key] = timestamps
                return False
            timestamps.append(now)
            self._windows[key] = timestamps
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
