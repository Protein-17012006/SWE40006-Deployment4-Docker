"""Version 1.1.0: polls can close after 1 hour, 1 day or 7 days."""

import json
from datetime import datetime, timedelta, timezone

import httpx
import pytest

from quickpoll.main import create_app
from quickpoll.validation import validate_poll
from tests.conftest import TEST_SETTINGS, csrf_token

START = datetime(2026, 10, 10, 9, 0, tzinfo=timezone.utc)


class Clock:
    def __init__(self, now: datetime) -> None:
        self.now = now

    def __call__(self) -> datetime:
        return self.now


@pytest.fixture
def clock():
    return Clock(START)


@pytest.fixture
async def client(repo, redis, clock):
    app = create_app(TEST_SETTINGS, repo=repo, redis=redis, clock=clock)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver") as c:
        yield c


async def create(client, close_after: str) -> str:
    token = await csrf_token(client)
    response = await client.post("/polls", data={"csrf_token": token, "question": "Lunch at noon?",
                                                  "option": ["Yes", "No"], "close_after": close_after})
    assert response.status_code == 303, response.text
    return response.headers["location"].rsplit("/", 1)[-1]


@pytest.mark.parametrize("value", ["never", "1h", "1d", "7d"])
def test_close_after_choices_are_valid(value):
    assert validate_poll("Lunch at noon?", ["Yes", "No"], value).close_after == value


@pytest.mark.parametrize("value", ["2h", "", None, ["1h"]])
def test_other_close_after_values_are_rejected(value):
    assert validate_poll("Lunch at noon?", ["Yes", "No"], value).errors["close_after"] == "Choose when the poll closes."


def test_close_after_defaults_to_never():
    assert validate_poll("Lunch at noon?", ["Yes", "No"]).close_after == "never"


async def test_home_page_offers_the_close_after_choices(client):
    page = (await client.get("/")).text
    assert '<select id="close_after" name="close_after">' in page
    assert '<option value="never" selected>Never</option>' in page
    assert '<option value="7d">7 days</option>' in page


async def test_closing_time_is_stored_from_the_clock(client, repo):
    slug = await create(client, "1h")
    assert repo.polls[slug].closes_at == START + timedelta(hours=1)
    never = await create(client, "never")
    assert repo.polls[never].closes_at is None


async def test_open_poll_says_when_it_closes(client):
    slug = await create(client, "1d")
    page = (await client.get(f"/p/{slug}")).text
    assert "Closes on 2026-10-11 09:00 UTC" in page
    assert 'name="option"' in page


async def test_closed_poll_refuses_votes_and_shows_results(client, repo, clock):
    slug = await create(client, "1h")
    poll = repo.polls[slug]
    clock.now = START + timedelta(hours=1)               # exactly at the closing time
    page = (await client.get(f"/p/{slug}")).text
    assert "This poll is closed. Closed on 2026-10-10 10:00 UTC." in page
    assert 'name="option"' not in page
    token = client.cookies["qp_csrf"]
    vote = await client.post(f"/p/{slug}/vote", data={"csrf_token": token, "option": str(poll.options[0].id)})
    assert vote.status_code == 303
    assert vote.headers["location"] == f"/p/{slug}/results?closed=1"
    assert repo.votes == {}
    results = (await client.get(f"/p/{slug}/results?closed=1")).text
    assert "This poll is closed." in results
    assert "Closed on 2026-10-10 10:00 UTC" in results


async def test_live_event_reports_a_closed_poll(repo, redis, clock):
    class NoUpdates:
        async def subscribe(self, poll_id, heartbeat=15.0):
            return
            yield

    app = create_app(TEST_SETTINGS, repo=repo, redis=redis, clock=clock)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver") as client:
        slug = await create(client, "1h")
        app.state.live = NoUpdates()
        clock.now = START + timedelta(days=1)
        stream = (await client.get(f"/p/{slug}/events")).text
    payload = json.loads(stream.split("data: ", 1)[1].split("\n", 1)[0])
    assert payload["closed"] is True


async def test_polls_from_version_1_0_0_never_close(client, repo, clock):
    poll = await repo.create_poll("Old poll", ["a", "b"])  # closes_at defaults to None, like rows from 1.0.0
    clock.now = START + timedelta(days=365)
    assert not poll.is_closed(clock())
    page = (await client.get(f"/p/{poll.slug}")).text
    assert 'name="option"' in page and "Closes on" not in page
