"""A small in-process rate limiter.

Scope, stated plainly: this is a spam brake, not a security boundary. State lives
in this process's memory, so it resets on restart and would not be shared across
workers. On one free instance running a single worker that is the honest ceiling —
anything stronger needs shared state (Redis), which this project does not pay for.

It is still worth having. Without it, one script can fill an ephemeral database
with predictions or grind a 0.1 vCPU instance to a halt.
"""
from __future__ import annotations

import threading
import time

from fastapi import HTTPException, Request

_BUCKETS: dict[tuple[str, str], tuple[float, float]] = {}
_LOCK = threading.Lock()
_MAX_TRACKED = 10_000


def client_ip(request: Request) -> str:
    """The visitor's address, not the proxy's.

    Both Vercel and Render sit in front of this app, so `request.client.host` is
    always one of their addresses — keying on it would rate-limit every visitor as
    if they were one caller. The left-most X-Forwarded-For entry is the original
    client. It is client-controlled and therefore spoofable; that is acceptable for
    a spam brake and would not be for anything stronger.
    """
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def limit(request: Request, name: str, capacity: int, per_seconds: float) -> None:
    """Token bucket. Raises 429 when the caller has spent its allowance.

    A bucket refills continuously rather than resetting on a fixed window, so a
    caller cannot burst the full allowance twice by straddling a window boundary.
    """
    key = (name, client_ip(request))
    now = time.monotonic()
    rate = capacity / per_seconds

    with _LOCK:
        # Unbounded growth is a memory leak on a long-lived process; a full reset
        # is crude but costs nothing and only ever grants extra allowance.
        if len(_BUCKETS) > _MAX_TRACKED:
            _BUCKETS.clear()

        tokens, last = _BUCKETS.get(key, (float(capacity), now))
        tokens = min(capacity, tokens + (now - last) * rate)
        if tokens < 1.0:
            retry_after = int((1.0 - tokens) / rate) + 1
            _BUCKETS[key] = (tokens, now)
            raise HTTPException(
                status_code=429,
                detail=f"Too many requests. Try again in {retry_after}s.",
                headers={"Retry-After": str(retry_after)},
            )
        _BUCKETS[key] = (tokens - 1.0, now)


def reset() -> None:
    """Clear all buckets. For tests."""
    with _LOCK:
        _BUCKETS.clear()
