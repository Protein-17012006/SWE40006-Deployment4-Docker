"""Shared fixtures: an in-memory repository and fakeredis, so route tests need no database."""

import itertools
import uuid
from datetime import datetime, timezone

import fakeredis
import httpx
import pytest

from quickpoll.config import Settings
from quickpoll.repository import DatabaseUnavailable, InvalidOption, Option, OptionResult, Poll, Results

TEST_SETTINGS = Settings(deploy_target="pytest", app_version="test")
CLIENT_IP = "203.0.113.7"


class FakeRepository:
    """Same interface as PollRepository, kept in memory. Set `down = True` to simulate an outage."""

    def __init__(self) -> None:
        self.polls: dict[str, Poll] = {}
        self.votes: dict[tuple[int, uuid.UUID], int] = {}
        self.down = False
        self._ids = itertools.count(1)

    def _check(self) -> None:
        if self.down:
            raise DatabaseUnavailable("connection refused")

    async def create_poll(self, question, options, closes_at=None, slug_factory=None):
        self._check()
        slug = f"poll{len(self.polls) + 1:04d}"
        poll = Poll(next(self._ids), slug, question, datetime.now(timezone.utc),
                    tuple(Option(next(self._ids), label) for label in options), closes_at)
        self.polls[slug] = poll
        return poll

    async def get_poll(self, slug):
        self._check()
        return self.polls.get(slug)

    async def has_voted(self, poll_id, voter_id):
        self._check()
        return (poll_id, voter_id) in self.votes

    async def record_vote(self, poll_id, option_id, voter_id):
        self._check()
        poll = next(p for p in self.polls.values() if p.id == poll_id)
        if not poll.has_option(option_id):
            raise InvalidOption(option_id)
        if (poll_id, voter_id) in self.votes:
            return False
        self.votes[(poll_id, voter_id)] = option_id
        return True

    async def results(self, poll):
        self._check()
        counts = [sum(1 for (pid, _), oid in self.votes.items() if pid == poll.id and oid == o.id)
                  for o in poll.options]
        return Results(poll, tuple(OptionResult(o.id, o.label, n) for o, n in zip(poll.options, counts)))

    async def ping(self):
        self._check()

    async def server_version(self):
        return None if self.down else "18.6"


@pytest.fixture
def repo():
    return FakeRepository()


@pytest.fixture
def redis():
    return fakeredis.FakeAsyncRedis()


@pytest.fixture
async def client(repo, redis):
    from quickpoll.main import create_app   # imported here so Task 12 can use this file before main.py exists

    app = create_app(TEST_SETTINGS, repo=repo, redis=redis)
    transport = httpx.ASGITransport(app=app, client=(CLIENT_IP, 50000))
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as c:
        yield c


async def csrf_token(client) -> str:
    """GET the home page so the CSRF cookie is set, and return it (the form repeats it)."""
    await client.get("/")
    return client.cookies["qp_csrf"]


async def make_poll(client, question="Which runtime?", options=("Docker", "Podman")) -> str:
    token = await csrf_token(client)
    response = await client.post("/polls", data={"csrf_token": token, "question": question, "option": list(options)})
    assert response.status_code == 303, response.text
    return response.headers["location"].rsplit("/", 1)[-1]
