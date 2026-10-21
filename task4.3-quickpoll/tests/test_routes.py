import json
import uuid

import httpx

from quickpoll.main import create_app
from tests.conftest import CLIENT_IP, TEST_SETTINGS, csrf_token, make_poll


async def test_home_sets_a_csrf_cookie_and_shows_where_it_runs(client):
    response = await client.get("/")
    assert response.status_code == 200
    token = client.cookies["qp_csrf"]
    assert f'name="csrf_token" value="{token}"' in response.text
    assert "Quick Poll test · pytest · host " in response.text
    assert "PostgreSQL 18.6" in response.text


async def test_create_poll_redirects_to_its_page(client, repo):
    slug = await make_poll(client, "Which runtime?", ["Docker", "Podman", ""])
    poll = repo.polls[slug]
    assert [o.label for o in poll.options] == ["Docker", "Podman"]
    page = await client.get(f"/p/{slug}")
    assert page.status_code == 200
    assert "Which runtime?" in page.text and 'value="' in page.text


async def test_invalid_poll_is_shown_again_with_messages(client, repo):
    token = await csrf_token(client)
    response = await client.post("/polls", data={"csrf_token": token, "question": "Which runtime?", "option": ["Docker"]})
    assert response.status_code == 422
    assert "Give between 2 and 6 options." in response.text
    assert 'value="Which runtime?"' in response.text
    assert repo.polls == {}


async def test_post_without_csrf_token_is_refused(client, repo):
    await client.get("/")
    response = await client.post("/polls", data={"question": "Which runtime?", "option": ["a", "b"]})
    assert response.status_code == 400
    assert "Form expired" in response.text
    assert repo.polls == {}


async def test_malformed_bodies_never_cause_a_500(client):
    await client.get("/")
    raw = await client.post("/polls", content=b"\xff\xfe garbage", headers={"Content-Type": "multipart/form-data"})
    upload = await client.post("/polls", files={"question": ("q.txt", b"file instead of text")})
    assert raw.status_code == 400
    assert upload.status_code == 400


async def test_sixth_poll_in_an_hour_is_rate_limited(client):
    for i in range(5):
        await make_poll(client, f"Question number {i}")
    token = client.cookies["qp_csrf"]
    response = await client.post("/polls", data={"csrf_token": token, "question": "One too many", "option": ["a", "b"]})
    assert response.status_code == 429
    assert int(response.headers["retry-after"]) > 0


async def test_unknown_and_malformed_slugs_are_404(client):
    assert (await client.get("/p/doesnotexist")).status_code == 404
    response = await client.get("/p/bad$slug")
    assert response.status_code == 404
    assert "That page or poll does not exist." in response.text


async def test_vote_records_once_and_sets_the_voter_cookie(client, repo, redis):
    slug = await make_poll(client)
    poll = repo.polls[slug]
    token = client.cookies["qp_csrf"]
    pubsub = redis.pubsub()
    await pubsub.subscribe(f"quickpoll:poll:{poll.id}")
    await pubsub.get_message(timeout=0.1)              # the subscribe confirmation

    first = await client.post(f"/p/{slug}/vote", data={"csrf_token": token, "option": str(poll.options[0].id)})
    assert first.status_code == 303
    assert first.headers["location"] == f"/p/{slug}/results"
    voter = uuid.UUID(client.cookies["qp_voter"])
    assert repo.votes == {(poll.id, voter): poll.options[0].id}
    message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1)
    assert message is not None and message["data"] == b"vote"

    second = await client.post(f"/p/{slug}/vote", data={"csrf_token": token, "option": str(poll.options[1].id)})
    assert second.headers["location"] == f"/p/{slug}/results?already=1"
    assert len(repo.votes) == 1
    await pubsub.aclose()


async def test_voter_who_already_voted_goes_straight_to_results(client, repo):
    slug = await make_poll(client)
    token = client.cookies["qp_csrf"]
    await client.post(f"/p/{slug}/vote", data={"csrf_token": token, "option": str(repo.polls[slug].options[0].id)})
    response = await client.get(f"/p/{slug}")
    assert response.status_code == 303
    assert response.headers["location"] == f"/p/{slug}/results"


async def test_invalid_options_are_rejected_with_422(client, repo):
    slug = await make_poll(client)
    other = await make_poll(client, "Another question", ["x", "y"])
    token = client.cookies["qp_csrf"]
    foreign_option = str(repo.polls[other].options[0].id)
    for bad in ["", "abc", "3.5", "999999", foreign_option]:
        response = await client.post(f"/p/{slug}/vote", data={"csrf_token": token, "option": bad})
        assert response.status_code == 422, bad
        assert "Choose one of the options." in response.text
    assert repo.votes == {}


async def test_results_page_shows_counts_percentages_and_notice(client, repo):
    slug = await make_poll(client)
    poll = repo.polls[slug]
    token = client.cookies["qp_csrf"]
    await client.post(f"/p/{slug}/vote", data={"csrf_token": token, "option": str(poll.options[1].id)})
    page = await client.get(f"/p/{slug}/results?already=1")
    assert page.status_code == 200
    assert "1 (100.0%)" in page.text and "0 (0.0%)" in page.text
    assert '<strong id="total">1</strong>' in page.text
    assert "You already voted in this poll." in page.text
    assert f'value="http://testserver/p/{slug}"' in page.text


async def test_events_endpoint_streams_a_snapshot(repo, redis):
    class OneShotLive:
        async def subscribe(self, poll_id, heartbeat=15.0):
            return
            yield  # an async generator that ends at once

    app = create_app(TEST_SETTINGS, repo=repo, redis=redis)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver") as client:
        slug = await make_poll(client)
        app.state.live = OneShotLive()
        response = await client.get(f"/p/{slug}/events")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert response.headers["x-accel-buffering"] == "no"
    assert response.text.startswith("retry: 3000\n\nevent: results\ndata: ")
    payload = json.loads(response.text.split("data: ", 1)[1].split("\n", 1)[0])
    assert payload["total"] == 0


async def test_database_outage_gives_a_friendly_503(client, repo):
    slug = await make_poll(client)
    repo.down = True
    page = await client.get(f"/p/{slug}")
    assert page.status_code == 503
    assert "Polls are temporarily unavailable." in page.text
    assert "PostgreSQL" not in page.text                 # footer leaves out the version while down
    token = client.cookies["qp_csrf"]
    create = await client.post("/polls", data={"csrf_token": token, "question": "Still there?", "option": ["a", "b"]})
    assert create.status_code == 503


async def test_redis_outage_does_not_stop_voting(repo):
    class DownRedis:
        async def incr(self, key):
            raise ConnectionError("redis down")

        async def publish(self, *args):
            raise ConnectionError("redis down")

        async def ping(self):
            raise ConnectionError("redis down")

    app = create_app(TEST_SETTINGS, repo=repo, redis=DownRedis())
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver") as client:
        slug = await make_poll(client)
        token = client.cookies["qp_csrf"]
        vote = await client.post(f"/p/{slug}/vote", data={"csrf_token": token, "option": str(repo.polls[slug].options[0].id)})
        ready = await client.get("/readyz")
    assert vote.status_code == 303
    assert ready.status_code == 503
    assert ready.json() == {"status": "unavailable", "database": "ok", "redis": "unavailable"}


async def test_health_and_readiness(client, repo):
    assert (await client.get("/healthz")).text == "ok"
    ready = await client.get("/readyz")
    assert ready.status_code == 200 and ready.json() == {"status": "ok", "database": "ok", "redis": "ok"}
    repo.down = True
    assert (await client.get("/healthz")).status_code == 200
    assert (await client.get("/readyz")).json()["database"] == "unavailable"


async def test_unexpected_errors_show_a_generic_500_page(repo, redis):
    async def explode(slug):
        raise RuntimeError("secret detail that must not leak")

    repo.get_poll = explode
    app = create_app(TEST_SETTINGS, repo=repo, redis=redis)
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False, client=(CLIENT_IP, 1))
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/p/abc")
    assert response.status_code == 500
    assert "Something went wrong on our side." in response.text
    assert "secret detail" not in response.text


async def test_rate_limit_is_per_forwarded_ip(client):
    token = await csrf_token(client)
    form = {"csrf_token": token, "question": "Per-IP limits?", "option": ["yes", "no"]}
    for _ in range(5):
        assert (await client.post("/polls", data=form, headers={"X-Real-IP": "198.51.100.1"})).status_code == 303
    assert (await client.post("/polls", data=form, headers={"X-Real-IP": "198.51.100.1"})).status_code == 429
    assert (await client.post("/polls", data=form, headers={"X-Real-IP": "198.51.100.2"})).status_code == 303


async def test_vietnamese_poll_round_trip(client, repo):
    slug = await make_poll(client, "Bạn thích món nào nhất?", ["Phở bò", "Bún chả"])
    vote_page = await client.get(f"/p/{slug}")
    assert vote_page.headers["content-type"] == "text/html; charset=utf-8"
    assert "Bạn thích món nào nhất?" in vote_page.text and "Phở bò" in vote_page.text
    token = client.cookies["qp_csrf"]
    await client.post(f"/p/{slug}/vote", data={"csrf_token": token, "option": str(repo.polls[slug].options[0].id)})
    results = (await client.get(f"/p/{slug}/results")).text
    assert "Phở bò" in results and "1 (100.0%)" in results


async def test_home_still_loads_while_the_database_is_down(client, repo):
    repo.down = True
    page = await client.get("/")
    assert page.status_code == 200
    assert "Create a poll" in page.text
