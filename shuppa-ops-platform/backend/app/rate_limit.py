"""A small, dependency-free per-IP rate limiter, applied as ASGI middleware
in app/main.py.

Design: fixed-window counter per client IP, kept in an in-memory dict. Every
request bumps a (count, window_start) tuple for that IP; once the window
(RATE_LIMIT_WINDOW_SECONDS) elapses the counter resets. If a client exceeds
RATE_LIMIT_REQUESTS within the current window, subsequent requests get a
429 until the window rolls over.

Deliberately NOT using a library like slowapi here to keep the dependency
list small for what is, for now, a single-process internal ops tool. Two
honest limitations worth knowing about if this ever goes multi-instance:

1. In-memory only - counters are per-process. Behind a load balancer with
   multiple backend instances/workers, each one enforces its own limit
   independently, so the effective limit is (RATE_LIMIT_REQUESTS * worker
   count), not a single global cap. A real deployment would want a shared
   store (e.g. Redis) instead.
2. No cleanup/eviction - the dict grows by one entry per distinct client IP
   ever seen. Fine for an internal tool with a small, stable set of users;
   would need periodic pruning for a public-facing API with many transient
   IPs.

Health checks (/health) and the root endpoint are exempt so uptime probes
never get throttled.

A second, much tighter bucket (LOGIN_RATE_LIMIT_REQUESTS per
LOGIN_RATE_LIMIT_WINDOW_SECONDS - see app/config.py) applies on top of the
general one, per-IP, to the credential-guessing-prone auth endpoints
(/auth/login, /auth/register, /auth/forgot-password). This is deliberately
separate from the per-account lockout in app/auth.py: the lockout stops
someone hammering one known username, while this stops someone rotating
through many usernames (or many registration/reset attempts) from the same
IP before the general 300-req/min limit would ever kick in.
"""

import time
from collections import defaultdict
from typing import Tuple

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from app.config import (
    LOGIN_RATE_LIMIT_REQUESTS,
    LOGIN_RATE_LIMIT_WINDOW_SECONDS,
    RATE_LIMIT_REQUESTS,
    RATE_LIMIT_WINDOW_SECONDS,
)

_EXEMPT_PATHS = {"/", "/health"}
_SENSITIVE_AUTH_PATHS = {"/auth/login", "/auth/register", "/auth/forgot-password"}


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(
        self,
        app,
        requests: int = RATE_LIMIT_REQUESTS,
        window_seconds: int = RATE_LIMIT_WINDOW_SECONDS,
        login_requests: int = LOGIN_RATE_LIMIT_REQUESTS,
        login_window_seconds: int = LOGIN_RATE_LIMIT_WINDOW_SECONDS,
    ):
        super().__init__(app)
        self.requests = requests
        self.window_seconds = window_seconds
        self.login_requests = login_requests
        self.login_window_seconds = login_window_seconds
        # client_ip -> (window_start_epoch_seconds, count_in_window)
        self._buckets: dict[str, Tuple[float, int]] = defaultdict(lambda: (0.0, 0))
        self._login_buckets: dict[str, Tuple[float, int]] = defaultdict(lambda: (0.0, 0))

    @staticmethod
    def _check(buckets: dict, key: str, limit: int, window_seconds: float, now: float):
        """Returns (allowed, retry_after_seconds). Shared fixed-window logic
        for both the general bucket and the tighter auth-path bucket."""
        window_start, count = buckets[key]
        if now - window_start >= window_seconds:
            window_start, count = now, 0
        count += 1
        buckets[key] = (window_start, count)
        if count > limit:
            return False, max(1, int(window_seconds - (now - window_start)))
        return True, 0

    async def dispatch(self, request: Request, call_next):
        if request.url.path in _EXEMPT_PATHS:
            return await call_next(request)

        client_ip = request.client.host if request.client else "unknown"
        now = time.time()

        if request.url.path in _SENSITIVE_AUTH_PATHS:
            allowed, retry_after = self._check(
                self._login_buckets, client_ip, self.login_requests, self.login_window_seconds, now
            )
            if not allowed:
                return JSONResponse(
                    status_code=429,
                    content={
                        "detail": (
                            f"Too many attempts ({self.login_requests} per "
                            f"{self.login_window_seconds}s) - please wait before trying again."
                        )
                    },
                    headers={"Retry-After": str(retry_after)},
                )

        allowed, retry_after = self._check(self._buckets, client_ip, self.requests, self.window_seconds, now)
        if not allowed:
            return JSONResponse(
                status_code=429,
                content={
                    "detail": (
                        f"Rate limit exceeded ({self.requests} requests per "
                        f"{self.window_seconds}s). Try again shortly."
                    )
                },
                headers={"Retry-After": str(retry_after)},
            )

        return await call_next(request)
