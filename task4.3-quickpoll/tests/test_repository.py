"""Repository tests against a real PostgreSQL (compose.test.yaml). Skipped without TEST_DATABASE_URL."""

import os
import uuid

import psycopg
import pytest
from psycopg_pool import AsyncConnectionPool

from quickpoll import migrate
from quickpoll.repository import DatabaseUnavailable, InvalidOption, PollRepository

DB_URL = os.environ.get("TEST_DATABASE_URL")
pytestmark = [
    pytest.mark.db,
    pytest.mark.skipif(not DB_URL, reason="TEST_DATABASE_URL is not set (run through compose.test.yaml)"),
]


@pytest.fixture
def fresh_schema():
    """Empty public schema, then all migrations, before every test."""
    with psycopg.connect(DB_URL, autocommit=True) as conn:
        conn.execute("DROP SCHEMA public CASCADE")
        conn.execute("CREATE SCHEMA public")
    migrate.run(DB_URL, out=lambda line: None)


@pytest.fixture
async def repo(fresh_schema):
    pool = AsyncConnectionPool(DB_URL, min_size=1, max_size=2, open=False)
    await pool.open(wait=True, timeout=10)
    yield PollRepository(pool)
    await pool.close()


async def test_create_and_get_a_poll_with_unicode_text(repo):
    poll = await repo.create_poll("Bạn thích gì nhất?", ["Phở", "Bún chả", "Bánh mì"])
    found = await repo.get_poll(poll.slug)
    assert found == poll
    assert [o.label for o in found.options] == ["Phở", "Bún chả", "Bánh mì"]
    assert len(poll.slug) == 8 and poll.slug.isalnum()


async def test_unknown_slug_is_none(repo):
    assert await repo.get_poll("nothere") is None


async def test_slug_collision_is_retried(repo):
    await repo.create_poll("First question", ["a", "b"], slug_factory=lambda: "AAAA1111")
    slugs = iter(["AAAA1111", "BBBB2222"])
    second = await repo.create_poll("Second question", ["c", "d"], slug_factory=lambda: next(slugs))
    assert second.slug == "BBBB2222"


async def test_one_vote_per_voter(repo):
    poll = await repo.create_poll("Which runtime?", ["Docker", "Podman"])
    voter = uuid.uuid4()
    assert not await repo.has_voted(poll.id, voter)
    assert await repo.record_vote(poll.id, poll.options[0].id, voter) is True
    assert await repo.has_voted(poll.id, voter)
    assert await repo.record_vote(poll.id, poll.options[1].id, voter) is False
    results = await repo.results(poll)
    assert [(o.label, o.votes) for o in results.options] == [("Docker", 1), ("Podman", 0)]


async def test_option_from_another_poll_is_rejected_by_the_database(repo):
    first = await repo.create_poll("First question", ["a", "b"])
    second = await repo.create_poll("Second question", ["c", "d"])
    with pytest.raises(InvalidOption):
        await repo.record_vote(first.id, second.options[0].id, uuid.uuid4())


async def test_results_keep_option_order_and_compute_percentages(repo):
    poll = await repo.create_poll("Pick a number", ["one", "two", "three"])
    for option in (poll.options[2], poll.options[2], poll.options[0]):
        await repo.record_vote(poll.id, option.id, uuid.uuid4())
    results = await repo.results(poll)
    assert [o.label for o in results.options] == ["one", "two", "three"]
    assert results.total == 3
    assert [results.percent(o.votes) for o in results.options] == [33.3, 0.0, 66.7]


async def test_server_version_is_postgresql_18(repo):
    assert (await repo.server_version()).startswith("18")


async def test_unreachable_database_raises_unavailable():
    pool = AsyncConnectionPool("host=127.0.0.1 port=1 dbname=x user=x connect_timeout=1",
                               min_size=1, max_size=1, open=False, timeout=1)
    await pool.open(wait=False)
    repo = PollRepository(pool)
    with pytest.raises(DatabaseUnavailable):
        await repo.get_poll("abc")
    assert await repo.server_version() is None
    await pool.close()


async def test_missing_schema_counts_as_unavailable():
    with psycopg.connect(DB_URL, autocommit=True) as conn:
        conn.execute("DROP SCHEMA public CASCADE")
        conn.execute("CREATE SCHEMA public")
    pool = AsyncConnectionPool(DB_URL, min_size=1, max_size=1, open=False)
    await pool.open(wait=True, timeout=10)
    with pytest.raises(DatabaseUnavailable):
        await PollRepository(pool).get_poll("abc")
    await pool.close()
