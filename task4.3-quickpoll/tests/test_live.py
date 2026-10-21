import json

import fakeredis
from redis.exceptions import ConnectionError as RedisConnectionError

from quickpoll.live import LiveUpdates, channel, event_stream
from tests.conftest import FakeRepository


class ScriptedLive:
    """Stands in for LiveUpdates.subscribe: yields a fixed list of events, then stops."""

    def __init__(self, events, fail=False):
        self.events = events
        self.fail = fail
        self.closed = False

    async def subscribe(self, poll_id, heartbeat=15.0):
        try:
            if self.fail:
                raise RedisConnectionError("Error 111 connecting to redis:6379")
            for event in self.events:
                yield event
        finally:
            self.closed = True


async def collect(stream) -> list[str]:
    return [chunk async for chunk in stream]


async def poll_with_votes(repo: FakeRepository):
    poll = await repo.create_poll("Which runtime?", ["Docker", "Podman"])
    await repo.record_vote(poll.id, poll.options[0].id, __import__("uuid").uuid4())
    return poll


async def test_stream_sends_retry_then_a_snapshot_then_one_event_per_vote():
    repo = FakeRepository()
    poll = await poll_with_votes(repo)
    live = ScriptedLive(["update", "heartbeat"])
    chunks = await collect(event_stream(poll, repo, live))
    assert chunks[0] == "retry: 3000\n\n"
    assert chunks[1].startswith("event: results\ndata: ")
    snapshot = json.loads(chunks[1].split("data: ", 1)[1])
    assert snapshot == {"total": 1, "options": [{"id": poll.options[0].id, "votes": 1, "percent": 100.0},
                                                {"id": poll.options[1].id, "votes": 0, "percent": 0.0}],
                        "closed": False}
    assert chunks[2].startswith("event: results\n")
    assert chunks[3] == ": keep-alive\n\n"
    assert live.closed


async def test_stream_ends_after_its_lifetime():
    repo = FakeRepository()
    poll = await poll_with_votes(repo)
    ticks = iter([0.0, 5.0, 11.0])
    live = ScriptedLive(["heartbeat"] * 10)
    chunks = await collect(event_stream(poll, repo, live, lifetime=10.0, clock=lambda: next(ticks)))
    assert chunks.count(": keep-alive\n\n") == 2
    assert live.closed


async def test_stream_reports_unavailable_when_redis_fails():
    repo = FakeRepository()
    poll = await poll_with_votes(repo)
    chunks = await collect(event_stream(poll, repo, ScriptedLive([], fail=True)))
    assert chunks[-1] == "event: unavailable\ndata: {}\n\n"


async def test_stream_reports_unavailable_when_the_database_fails():
    repo = FakeRepository()
    poll = await poll_with_votes(repo)
    repo.down = True
    chunks = await collect(event_stream(poll, repo, ScriptedLive(["update"])))
    assert chunks == ["retry: 3000\n\n", "event: unavailable\ndata: {}\n\n"]


async def test_publish_and_subscribe_through_redis():
    redis = fakeredis.FakeAsyncRedis()
    live = LiveUpdates(redis)
    updates = live.subscribe(7, heartbeat=0.05)
    assert await updates.__anext__() == "heartbeat"     # subscribed, nothing published yet
    await live.publish(7)
    assert await updates.__anext__() == "update"
    await updates.aclose()
    assert channel(7) == "quickpoll:poll:7"


async def test_publish_ignores_a_redis_outage():
    class Broken:
        async def publish(self, *args):
            raise RedisConnectionError("down")

    await LiveUpdates(Broken()).publish(1)              # logs a warning, does not raise
