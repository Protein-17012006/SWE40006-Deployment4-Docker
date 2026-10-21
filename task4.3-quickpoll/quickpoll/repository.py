"""PostgreSQL access through an async psycopg 3 connection pool. All SQL lives here."""

import secrets
import string
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable

import psycopg
from psycopg import errors as pg_errors
from psycopg_pool import AsyncConnectionPool, PoolTimeout

SLUG_ALPHABET = string.ascii_letters + string.digits
SLUG_LENGTH = 8
SLUG_ATTEMPTS = 5


def new_slug() -> str:
    return "".join(secrets.choice(SLUG_ALPHABET) for _ in range(SLUG_LENGTH))


class DatabaseUnavailable(Exception):
    """PostgreSQL could not be reached, timed out, or has no schema yet."""


class InvalidOption(Exception):
    """The option does not belong to the poll (rejected by the composite foreign key)."""


@dataclass(frozen=True)
class Option:
    id: int
    label: str


@dataclass(frozen=True)
class Poll:
    id: int
    slug: str
    question: str
    created_at: datetime
    options: tuple[Option, ...]
    closes_at: datetime | None = None

    def is_closed(self, now: datetime) -> bool:
        return self.closes_at is not None and now >= self.closes_at

    def has_option(self, option_id: int) -> bool:
        return any(option.id == option_id for option in self.options)


@dataclass(frozen=True)
class OptionResult:
    id: int
    label: str
    votes: int


@dataclass(frozen=True)
class Results:
    poll: Poll
    options: tuple[OptionResult, ...]

    @property
    def total(self) -> int:
        return sum(option.votes for option in self.options)

    def percent(self, votes: int) -> float:
        return round(100 * votes / self.total, 1) if self.total else 0.0

    def as_event(self, now: datetime | None = None) -> dict:
        return {
            "total": self.total,
            "options": [{"id": o.id, "votes": o.votes, "percent": self.percent(o.votes)} for o in self.options],
            "closed": self.poll.is_closed(now or datetime.now(timezone.utc)),
        }


_UNAVAILABLE = (psycopg.OperationalError, PoolTimeout, pg_errors.UndefinedTable)


class PollRepository:
    def __init__(self, pool: AsyncConnectionPool) -> None:
        self._pool = pool
        self._server_version: str | None = None

    async def create_poll(self, question: str, options: list[str], closes_at: datetime | None = None,
                          slug_factory: Callable[[], str] = new_slug) -> Poll:
        for _ in range(SLUG_ATTEMPTS):
            slug = slug_factory()
            try:
                return await self._insert_poll(slug, question, options, closes_at)
            except pg_errors.UniqueViolation:
                continue  # slug taken: try another one
        raise RuntimeError(f"no free slug after {SLUG_ATTEMPTS} attempts")

    async def _insert_poll(self, slug: str, question: str, options: list[str], closes_at: datetime | None) -> Poll:
        try:
            async with self._pool.connection() as conn, conn.transaction():
                cur = await conn.execute(
                    "INSERT INTO polls (slug, question, closes_at) VALUES (%s, %s, %s) RETURNING id, created_at",
                    (slug, question, closes_at),
                )
                poll_id, created_at = await cur.fetchone()
                saved = []
                for position, label in enumerate(options, start=1):
                    cur = await conn.execute(
                        "INSERT INTO options (poll_id, position, label) VALUES (%s, %s, %s) RETURNING id",
                        (poll_id, position, label),
                    )
                    (option_id,) = await cur.fetchone()
                    saved.append(Option(option_id, label))
                return Poll(poll_id, slug, question, created_at, tuple(saved), closes_at)
        except _UNAVAILABLE as exc:
            raise DatabaseUnavailable(str(exc)) from exc

    async def get_poll(self, slug: str) -> Poll | None:
        try:
            async with self._pool.connection() as conn:
                cur = await conn.execute("SELECT id, slug, question, created_at, closes_at FROM polls WHERE slug = %s", (slug,))
                row = await cur.fetchone()
                if row is None:
                    return None
                cur = await conn.execute(
                    "SELECT id, label FROM options WHERE poll_id = %s ORDER BY position", (row[0],)
                )
                options = tuple(Option(option_id, label) for option_id, label in await cur.fetchall())
                return Poll(row[0], row[1], row[2], row[3], options, row[4])
        except _UNAVAILABLE as exc:
            raise DatabaseUnavailable(str(exc)) from exc

    async def has_voted(self, poll_id: int, voter_id: uuid.UUID) -> bool:
        try:
            async with self._pool.connection() as conn:
                cur = await conn.execute(
                    "SELECT 1 FROM votes WHERE poll_id = %s AND voter_id = %s", (poll_id, voter_id)
                )
                return await cur.fetchone() is not None
        except _UNAVAILABLE as exc:
            raise DatabaseUnavailable(str(exc)) from exc

    async def record_vote(self, poll_id: int, option_id: int, voter_id: uuid.UUID) -> bool:
        """Store a vote. False if this voter already voted on this poll."""
        try:
            async with self._pool.connection() as conn:
                cur = await conn.execute(
                    "INSERT INTO votes (poll_id, option_id, voter_id) VALUES (%s, %s, %s) "
                    "ON CONFLICT (poll_id, voter_id) DO NOTHING RETURNING id",
                    (poll_id, option_id, voter_id),
                )
                return await cur.fetchone() is not None
        except pg_errors.ForeignKeyViolation as exc:
            raise InvalidOption(f"option {option_id} is not part of poll {poll_id}") from exc
        except _UNAVAILABLE as exc:
            raise DatabaseUnavailable(str(exc)) from exc

    async def results(self, poll: Poll) -> Results:
        try:
            async with self._pool.connection() as conn:
                cur = await conn.execute(
                    "SELECT o.id, o.label, count(v.id) FROM options o "
                    "LEFT JOIN votes v ON v.option_id = o.id "
                    "WHERE o.poll_id = %s GROUP BY o.id, o.label, o.position ORDER BY o.position",
                    (poll.id,),
                )
                rows = await cur.fetchall()
        except _UNAVAILABLE as exc:
            raise DatabaseUnavailable(str(exc)) from exc
        return Results(poll, tuple(OptionResult(option_id, label, votes) for option_id, label, votes in rows))

    async def ping(self) -> None:
        try:
            async with self._pool.connection() as conn:
                await conn.execute("SELECT 1")
        except _UNAVAILABLE as exc:
            raise DatabaseUnavailable(str(exc)) from exc

    async def server_version(self) -> str | None:
        """PostgreSQL version for the footer, cached after the first success; None while unreachable."""
        if self._server_version is None:
            try:
                async with self._pool.connection() as conn:
                    cur = await conn.execute("SHOW server_version")
                    (value,) = await cur.fetchone()
                    self._server_version = value.split()[0]
            except _UNAVAILABLE:
                return None
        return self._server_version
