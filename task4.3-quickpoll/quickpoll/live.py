"""Live results: a vote publishes a nudge on Redis; every open results page re-reads the counts.

PostgreSQL stays the single source of truth; Redis only says "something changed".
"""

import json
import logging
import time
from contextlib import aclosing
from typing import AsyncIterator, Callable

from redis.exceptions import RedisError

from .repository import DatabaseUnavailable

log = logging.getLogger("quickpoll.live")

HEARTBEAT_SECONDS = 15.0
STREAM_LIFETIME_SECONDS = 600.0


def channel(poll_id: int) -> str:
    return f"quickpoll:poll:{poll_id}"


class LiveUpdates:
    def __init__(self, redis) -> None:
        self._redis = redis

    async def publish(self, poll_id: int) -> None:
        try:
            await self._redis.publish(channel(poll_id), "vote")
        except (RedisError, OSError) as exc:
            log.warning("live update not published: %s", exc)

    async def subscribe(self, poll_id: int, heartbeat: float = HEARTBEAT_SECONDS) -> AsyncIterator[str]:
        """Yield "update" after each vote and "heartbeat" after `heartbeat` quiet seconds."""
        pubsub = self._redis.pubsub()
        try:
            await pubsub.subscribe(channel(poll_id))
            while True:
                message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=heartbeat)
                yield "update" if message else "heartbeat"
        finally:
            await pubsub.aclose()


def sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, separators=(',', ':'))}\n\n"


async def event_stream(poll, repo, live, lifetime: float = STREAM_LIFETIME_SECONDS,
                       clock: Callable[[], float] = time.monotonic) -> AsyncIterator[str]:
    """Server-Sent Events for one results page: a snapshot first, then one event per vote."""
    yield "retry: 3000\n\n"
    deadline = clock() + lifetime
    try:
        yield sse("results", (await repo.results(poll)).as_event())
        async with aclosing(live.subscribe(poll.id)) as updates:   # always unsubscribes
            async for kind in updates:
                if kind == "update":
                    yield sse("results", (await repo.results(poll)).as_event())
                else:
                    yield ": keep-alive\n\n"
                if clock() >= deadline:
                    break  # the browser reconnects on its own after `retry`
    except (RedisError, OSError, DatabaseUnavailable) as exc:
        log.warning("live results stopped for poll %s: %s", poll.id, exc)
        yield sse("unavailable", {})
