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


def _redis():
    global _redis_client
    if _redis_client is None and redis is not None:
        try:
            _redis_client = redis.from_url(settings.redis_url, socket_connect_timeout=0.5, socket_timeout=0.5, decode_responses=True)
            _redis_client.ping()
        except Exception:
            _redis_client = False
    return _redis_client if _redis_client is not False else None


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
            pass
    now = time.monotonic()
    with _lock:
        bucket = _events[key]
        while bucket and bucket[0] <= now - 60:
            bucket.popleft()
        if len(bucket) >= settings.rate_limit_per_minute:
            raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="rate_limit_exceeded")
        bucket.append(now)
