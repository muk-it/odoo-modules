from __future__ import annotations

import time
from collections.abc import Callable

FLUSH_CHARS = 80
FLUSH_SECONDS = 0.1


class StreamBuffer:
    """Coalesce streamed deltas into events of 80 characters or 0.1 seconds.

    ``text`` holds the answer streamed so far; ``turn``, ``checked`` and
    ``beat`` belong to the caller, which polls the session while it streams.
    """

    def __init__(
        self, publish: Callable[[str, dict], None], turn: int | None = None
    ) -> None:
        """Send each coalesced delta through ``publish(event_type, payload)``."""
        self.publish = publish
        self.turn = turn
        self.text = ''
        self.checked = self.beat = 0.0
        self.pending: dict[tuple, list] = {}

    def add(self, event_type: str, delta: str, **extra) -> None:
        """Buffer a delta and publish the buffer once it is big or old enough."""
        now = time.monotonic()
        entry = self.pending.setdefault((event_type, *extra.items()), ['', now])
        entry[0] += delta
        if len(entry[0]) >= FLUSH_CHARS or now - entry[1] >= FLUSH_SECONDS:
            self.publish(event_type, {'delta': entry[0], **extra})
            entry[:] = ['', now]

    def flush(self, *event_types: str) -> None:
        """Publish what is buffered, of the given event types or of all."""
        for (event_type, *extra), entry in self.pending.items():
            if entry[0] and (not event_types or event_type in event_types):
                self.publish(event_type, {'delta': entry[0], **dict(extra)})
                entry[0] = ''
