"""A tiny in-memory, per-client rate limiter (sliding window) for the public deployment.

State lives in this process only: nothing is stored on disk and nothing identifies a person
beyond an IP address kept in memory for the length of the window. With several worker
processes each one counts separately, so the real limit is roughly workers x limit. That is
fine for abuse protection on a free demo; a shared store (Redis) would be the next step.
"""

import threading
import time
from collections import deque
from collections.abc import Callable

MAX_TRACKED_CLIENTS = 10_000  # hard cap so a flood of fake IPs cannot grow memory forever


class RateLimiter:
    """Allow at most `max_requests` per `window_seconds` for each key. `max_requests=0` disables."""

    def __init__(
        self,
        max_requests: int,
        window_seconds: float,
        clock: Callable[[], float] = time.monotonic,
    ):
        self.max_requests = max_requests
        self.window = window_seconds
        self._clock = clock
        self._hits: dict[str, deque[float]] = {}
        self._lock = threading.Lock()

    def check(self, key: str) -> int | None:
        """Record a request. Returns None if allowed, else seconds until a slot frees up."""
        if self.max_requests <= 0:
            return None
        now = self._clock()
        with self._lock:
            hits = self._hits.setdefault(key, deque())
            while hits and now - hits[0] >= self.window:
                hits.popleft()
            if len(hits) >= self.max_requests:
                return max(1, int(self.window - (now - hits[0])) + 1)
            hits.append(now)
            if len(self._hits) > MAX_TRACKED_CLIENTS:
                self._purge(now)
            return None

    def _purge(self, now: float) -> None:
        """Drop clients with no recent hits; if still too many, drop the oldest ones."""
        for key in [
            k for k, hits in self._hits.items() if not hits or now - hits[-1] >= self.window
        ]:
            del self._hits[key]
        overflow = len(self._hits) - MAX_TRACKED_CLIENTS
        if overflow > 0:
            oldest = sorted(self._hits, key=lambda k: self._hits[k][-1])[:overflow]
            for key in oldest:
                del self._hits[key]


def client_key(client_host: str | None, forwarded_for: str | None, trust_proxy: bool) -> str:
    """The IP to count against.

    X-Forwarded-For is only believed when `trust_proxy` is set (the app runs behind a proxy
    such as Render's). The LAST entry is the one our own proxy appended; earlier entries can be
    forged by the client.
    """
    if trust_proxy and forwarded_for:
        last = forwarded_for.split(",")[-1].strip()
        if last:
            return last
    return client_host or "unknown"
