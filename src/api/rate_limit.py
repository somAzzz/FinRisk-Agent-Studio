"""In-process rate limiter middleware (R1 supplement to P0.1 auth).

A token-bucket / sliding-window rate limiter implemented with
:mod:`collections.deque` and the stdlib clock — no extra
dependencies. It is intentionally simple:

- One bucket per (API key or remote IP).
- ``RATE_LIMIT_RPM`` requests per 60 s window, ``RATE_LIMIT_BURST``
  as the bucket size (defaults to the same value).
- 429 responses carry a ``Retry-After`` header in seconds.
- ``RATE_LIMIT_DISABLED=1`` short-circuits the check entirely so
  tests and the local handler-direct suite do not need to clear
  buckets.

Limitations (acceptable for an internal demo tool, call out in
docs):

- Process-local state. Multiple uvicorn workers do not share
  buckets; an attacker can scale their effective rate by ``N`` by
  hitting the worker that knows their key least well. A multi-
  worker deployment should swap this for Redis.
- The 60 s window is fixed; finer-grained windows are out of scope.
"""

from __future__ import annotations

import os
import time
from collections import defaultdict, deque
from collections.abc import Awaitable, Callable

from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

_WINDOW_SECONDS = 60
_HEADER_NAME = "X-API-Key"


def _is_disabled() -> bool:
    return os.environ.get("RATE_LIMIT_DISABLED") == "1"


def _read_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


class SlidingWindowLimiter:
    """Per-key sliding window over the last ``window_seconds`` seconds."""

    def __init__(self, *, max_requests: int, window_seconds: int = _WINDOW_SECONDS) -> None:
        if max_requests <= 0:
            raise ValueError("max_requests must be > 0")
        self._max = max_requests
        self._window = window_seconds
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    def check(self, key: str, *, now: float | None = None) -> tuple[bool, int]:
        """Return ``(allowed, retry_after_seconds)`` for the given key.

        ``retry_after_seconds`` is ``0`` when the request is allowed.
        """
        if not key:
            # Defensive: never key on empty strings. A caller that has
            # no key material at all should bypass the limiter; auth
            # (P0.1) will reject the request anyway.
            return True, 0
        ts = time.monotonic() if now is None else now
        bucket = self._hits[key]
        # Drop entries that fell out of the window.
        cutoff = ts - self._window
        while bucket and bucket[0] <= cutoff:
            bucket.popleft()
        if len(bucket) >= self._max:
            # Retry-After = time until the oldest in-window hit ages out.
            wait = max(1, int(bucket[0] + self._window - ts) + 1)
            return False, wait
        bucket.append(ts)
        return True, 0

    def reset(self) -> None:
        """Clear every bucket. Test-only convenience."""
        self._hits.clear()


def _key_for(request: Request) -> str:
    api_key = request.headers.get(_HEADER_NAME)
    if api_key:
        return f"key:{api_key}"
    client = request.client
    if client is not None:
        return f"ip:{client.host}"
    return ""


class RateLimitMiddleware(BaseHTTPMiddleware):
    """FastAPI / Starlette middleware that enforces the rate limit.

    Accepts either a fixed ``limiter`` instance or a ``get_limiter``
    factory. The factory form lets tests reconfigure the limiter
    (e.g. via ``monkeypatch.setenv("RATE_LIMIT_RPM", ...)``) without
    rebuilding the middleware.
    """

    def __init__(
        self,
        app,
        *,
        limiter: SlidingWindowLimiter | None = None,
        get_limiter: Callable[[], SlidingWindowLimiter] | None = None,
    ) -> None:
        super().__init__(app)
        if (limiter is None) == (get_limiter is None):
            raise ValueError("Pass exactly one of `limiter` or `get_limiter`.")
        self._fixed = limiter
        self._getter = get_limiter

    def _limiter(self) -> SlidingWindowLimiter:
        if self._fixed is not None:
            return self._fixed
        assert self._getter is not None
        return self._getter()

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        if _is_disabled():
            return await call_next(request)
        key = _key_for(request)
        allowed, retry_after = self._limiter().check(key)
        if not allowed:
            return JSONResponse(
                status_code=429,
                content={"detail": "Rate limit exceeded."},
                headers={"Retry-After": str(retry_after)},
            )
        return await call_next(request)


def build_default_limiter() -> SlidingWindowLimiter:
    """Construct a limiter from the ``RATE_LIMIT_*`` env vars."""
    rpm = _read_int("RATE_LIMIT_RPM", 120)
    burst = _read_int("RATE_LIMIT_BURST", rpm)
    return SlidingWindowLimiter(max_requests=burst, window_seconds=_WINDOW_SECONDS)


__all__ = [
    "RateLimitMiddleware",
    "SlidingWindowLimiter",
    "build_default_limiter",
]
