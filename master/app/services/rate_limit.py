from __future__ import annotations

import time
from collections import defaultdict, deque
from threading import Lock

from fastapi import HTTPException, Request, status

from app.core.config import settings

try:
    import redis
except ImportError:  # pragma: no cover
    redis = None

_events: defaultdict[str, deque[float]] = defaultdict(deque)
_lock = Lock()
_redis_client = None
_redis_disabled_until = 0.0


def _redis():
    global _redis_client, _redis_disabled_until
    if redis is None:
        return None
    now = time.monotonic()
    if _redis_client is False and now < _redis_disabled_until:
        return None
    if _redis_client is None or (_redis_client is False and now >= _redis_disabled_until):
        try:
            _redis_client = redis.from_url(
                settings.redis_url,
                socket_connect_timeout=0.5,
                socket_timeout=0.5,
                decode_responses=True,
            )
            _redis_client.ping()
            _redis_disabled_until = 0.0
        except Exception:
            _redis_client = False
            _redis_disabled_until = now + 30.0
            return None
    return _redis_client if _redis_client is not False else None


def _local_enforce(key: str, now: float) -> None:
    with _lock:
        bucket = _events[key]
        cutoff = now - 60
        while bucket and bucket[0] <= cutoff:
            bucket.popleft()
        if len(bucket) >= settings.rate_limit_per_minute:
            raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="rate_limit_exceeded")
        bucket.append(now)

        # Bound memory even when an attacker rotates source IPs continuously.
        if len(_events) > 10000:
            stale_keys = [name for name, values in _events.items() if not values or values[-1] <= cutoff]
            for name in stale_keys[: max(0, len(_events) - 5000)]:
                _events.pop(name, None)


def enforce(request: Request) -> None:
    key = (request.client.host if request.client else "unknown")[:64]
    redis_client = _redis()
    if redis_client:
        bucket = f"pars2ray:ratelimit:{key}:{int(time.time() // 60)}"
        try:
            count = int(redis_client.incr(bucket))
            if count == 1:
                redis_client.expire(bucket, 65)
            if count > settings.rate_limit_per_minute:
                raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="rate_limit_exceeded")
            return
        except HTTPException:
            raise
        except Exception:
            global _redis_client, _redis_disabled_until
            _redis_client = False
            _redis_disabled_until = time.monotonic() + 30.0

    _local_enforce(key, time.monotonic())
