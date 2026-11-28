"""A small in-memory rate limiter: at most N requests per visitor per time window.

Why: every question costs Groq tokens, and the free tier allows ~100 questions a day in
total. Without a limit, one person (or one script) could use up everybody's questions in a
minute. Each visitor is identified by their IP address.

How: for every visitor we remember the times of their recent requests (a "sliding window").
A new request is allowed if fewer than `limit` of them fall inside the last `window` seconds.

Privacy: IP addresses live only in this process's memory, only as long as the window, and are
never written to the database or the logs.

Limitation: memory is per process. That's fine for one small server (our free Render
instance); with several servers you'd keep the counts in a shared store such as Redis.
"""

import math
import time
from collections import deque
from collections.abc import Callable
from threading import Lock

MINUTE = 60.0
DAY = 24 * 60 * 60.0


class RateLimiter:
    def __init__(
        self, limit: int, window: float, clock: Callable[[], float] = time.monotonic
    ) -> None:
        self.limit = limit
        self.window = window
        self.clock = clock  # replaceable in tests, so they don't have to wait a real minute
        self._hits: dict[str, deque[float]] = {}
        self._lock = Lock()  # FastAPI runs normal `def` endpoints in several threads at once

    def hit(self, key: str) -> float:
        """Record a request from `key`. Returns 0 if allowed, else seconds until it would be."""
        now = self.clock()
        with self._lock:
            hits = self._hits.setdefault(key, deque())
            while hits and hits[0] <= now - self.window:  # forget requests outside the window
                hits.popleft()
            if len(hits) >= self.limit:
                return hits[0] + self.window - now  # when the oldest request leaves the window
            hits.append(now)
            if len(self._hits) > 10_000:
                self._forget_idle(now)
            return 0.0

    def _forget_idle(self, now: float) -> None:
        """Drop visitors with no recent requests, so memory doesn't grow forever."""
        idle = [
            key for key, hits in self._hits.items() if not hits or hits[-1] <= now - self.window
        ]
        for key in idle:
            del self._hits[key]

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()


def retry_after_header(seconds: float) -> dict[str, str]:
    """HTTP's Retry-After header: whole seconds, rounded up, at least 1."""
    return {"Retry-After": str(max(1, math.ceil(seconds)))}
