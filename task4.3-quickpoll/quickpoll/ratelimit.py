"""Fixed-window rate limits kept in Redis. If Redis is down the limiter lets requests through."""

import logging
import time
from typing import Callable

from redis.exceptions import RedisError

log = logging.getLogger("quickpoll.ratelimit")


class RateLimiter:
    def __init__(self, redis, clock: Callable[[], float] = time.time) -> None:
        self._redis = redis
        self._clock = clock

    async def hit(self, action: str, client_ip: str, limit: int, window_seconds: int) -> int | None:
        """Count one request. Return None if allowed, or the seconds until the window resets."""
        now = self._clock()
        key = f"quickpoll:rl:{action}:{client_ip}:{int(now // window_seconds)}"
        try:
            count = await self._redis.incr(key)
            if count == 1:
                await self._redis.expire(key, window_seconds)
        except (RedisError, OSError) as exc:
            log.warning("rate limiter unavailable, allowing the request: %s", exc)
            return None
        if count > limit:
            return max(1, window_seconds - int(now % window_seconds))
        return None
