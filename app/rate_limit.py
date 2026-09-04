from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass

from fastapi import HTTPException, Request, status

from .config import settings
from .queue import get_redis_connection

logger = logging.getLogger(__name__)

_FIXED_WINDOW = """
local current = redis.call('INCR', KEYS[1])
if current == 1 then redis.call('EXPIRE', KEYS[1], ARGV[1]) end
return current
"""


@dataclass(frozen=True)
class Limit:
    requests: int
    seconds: int


def parse_limit(value: str) -> Limit:
    try:
        requests, seconds = (int(part) for part in value.split("/", 1))
    except (TypeError, ValueError) as exc:
        raise RuntimeError(f"Invalid rate limit configuration: {value!r}") from exc
    if requests < 1 or seconds < 1:
        raise RuntimeError("Rate limit values must be positive")
    return Limit(requests, seconds)


def client_address(request: Request) -> str:
    if settings.trust_proxy_headers:
        forwarded = request.headers.get("x-forwarded-for", "")
        if forwarded:
            return forwarded.split(",", 1)[0].strip()
    return request.client.host if request.client else "unknown"


def rate_limit(setting_name: str, scope: str):
    async def enforce(request: Request) -> None:
        if not settings.rate_limit_enabled:
            return
        limit = parse_limit(getattr(settings, setting_name))
        identity = hashlib.sha256(client_address(request).encode()).hexdigest()[:24]
        key = f"mindmate:rate:{scope}:{identity}"
        try:
            redis = get_redis_connection()
            count = redis.eval(_FIXED_WINDOW, 1, key, limit.seconds)
        except Exception as exc:
            # Availability is preferred here; authentication still applies normally.
            logger.warning("Rate limiter unavailable (%s)", type(exc).__name__)
            return
        if count > limit.requests:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many attempts. Please try again later.",
                headers={"Retry-After": str(limit.seconds)},
            )

    return enforce
