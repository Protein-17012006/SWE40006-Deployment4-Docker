"""Leaderboard stored in SQLite (scores.db in the data directory, a Docker volume in containers)."""

import sqlite3
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

OUTCOMES = ("win", "loss", "draw")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS results (
    id        INTEGER PRIMARY KEY,
    name      TEXT    NOT NULL,
    level     INTEGER NOT NULL,
    outcome   TEXT    NOT NULL CHECK (outcome IN ('win', 'loss', 'draw')),
    moves     INTEGER NOT NULL,
    played_at TEXT    NOT NULL
)
"""

# A win scores its level: Easy 1, Normal 2, Hard 3.
_TOP = """
SELECT name,
       SUM(CASE WHEN outcome = 'win' THEN level ELSE 0 END) AS score,
       SUM(outcome = 'win')  AS wins,
       SUM(outcome = 'loss') AS losses,
       SUM(outcome = 'draw') AS draws,
       MIN(CASE WHEN outcome = 'win' THEN moves END) AS fastest
FROM results
GROUP BY name
ORDER BY score DESC, losses ASC, name ASC
LIMIT ?
"""


@dataclass(frozen=True)
class Standing:
    rank: int
    name: str
    score: int
    wins: int
    losses: int
    draws: int
    fastest: int | None


class ScoreStore:
    """Thread-safe: the TCP server records results from worker threads."""

    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(path, check_same_thread=False)
        with self._lock:
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute(_SCHEMA)
            self._conn.commit()

    def record(self, name: str, level: int, outcome: str, moves: int, played_at: datetime | None = None) -> None:
        if outcome not in OUTCOMES:
            raise ValueError(f"unknown outcome {outcome!r}")
        stamp = (played_at or datetime.now(timezone.utc)).isoformat(timespec="seconds")
        with self._lock:
            self._conn.execute(
                "INSERT INTO results (name, level, outcome, moves, played_at) VALUES (?, ?, ?, ?, ?)",
                (name, level, outcome, moves, stamp),
            )
            self._conn.commit()

    def top(self, limit: int = 10) -> list[Standing]:
        with self._lock:
            rows = self._conn.execute(_TOP, (limit,)).fetchall()
        return [Standing(rank, *row) for rank, row in enumerate(rows, start=1)]

    def close(self) -> None:
        with self._lock:
            self._conn.close()
