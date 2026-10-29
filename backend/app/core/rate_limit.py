"""In-memory rate limiting for sensitive endpoints.

Intentionally simple and dependency-free. Known limitations:

- State lives in process memory: counters reset on restart and are NOT
  shared across multiple workers or instances. A multi-process
  production deployment needs a shared store (e.g. Redis) or a
  gateway/reverse-proxy level limiter instead.
- Clients are identified by the direct connection's IP address
  (request.client.host). When deployed behind a reverse proxy, run
  Uvicorn with --proxy-headers and trust only your own proxy's
  forwarding headers; never trust arbitrary X-Forwarded-For values
  sent by clients.

The limiter instances are module-level so all requests in the process
share them. Tests reset them between runs via reset().
"""

import threading
import time
from collections import deque
from collections.abc import Callable

from fastapi import HTTPException, Request, status


class InMemoryRateLimiter:
    """Fixed-window rate limiter keyed by an arbitrary string."""

    def __init__(self, max_attempts: int, window_seconds: float) -> None:
        if max_attempts < 1:
            raise ValueError("max_attempts must be at least 1.")
        if window_seconds <= 0:
            raise ValueError("window_seconds must be positive.")

        self.max_attempts = max_attempts
        self.window_seconds = window_seconds
        self._attempts: dict[str, deque[float]] = {}
        self._lock = threading.Lock()

    def is_allowed(self, key: str) -> bool:
        """Record an attempt; return False when the limit is exceeded."""
        now = time.monotonic()

        with self._lock:
            attempts = self._attempts.setdefault(key, deque())

            while attempts and attempts[0] <= now - self.window_seconds:
                attempts.popleft()

            if len(attempts) >= self.max_attempts:
                return False

            attempts.append(now)
            return True

    def reset(self) -> None:
        with self._lock:
            self._attempts.clear()


login_rate_limiter = InMemoryRateLimiter(
    max_attempts=5,
    window_seconds=60,
)
register_rate_limiter = InMemoryRateLimiter(
    max_attempts=10,
    window_seconds=60,
)
# Public receipt verification: generous for real checks, blocks scraping.
verify_rate_limiter = InMemoryRateLimiter(
    max_attempts=30,
    window_seconds=60,
)


def _client_key(request: Request) -> str:
    if request.client is None or not request.client.host:
        return "unknown"
    return request.client.host


def rate_limit(limiter: InMemoryRateLimiter) -> Callable[[Request], None]:
    """Build a FastAPI dependency that enforces the given limiter."""

    def dependency(request: Request) -> None:
        if not limiter.is_allowed(_client_key(request)):
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many attempts. Please try again later.",
            )

    return dependency
