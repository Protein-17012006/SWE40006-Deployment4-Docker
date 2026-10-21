"""Apply migrations/NNN_*.sql in order and seed the demo poll.

Run as a one-shot container before the web app starts:  python -m quickpoll.migrate
"""

import os
import sys
from pathlib import Path
from typing import Callable

import psycopg

from .config import load_settings

MIGRATIONS_DIR = Path(os.environ.get("MIGRATIONS_DIR", Path(__file__).resolve().parent.parent / "migrations"))
LOCK_ID = 4004  # pg_advisory_lock key: two runners never apply migrations at the same time

DEMO_SLUG = "docker"
DEMO_QUESTION = "Which Docker feature do you use most?"
DEMO_OPTIONS = ("Images and layers", "Volumes", "Docker Compose", "Networks")


def seed_demo(conn: psycopg.Connection) -> bool:
    with conn.transaction():
        row = conn.execute(
            "INSERT INTO polls (slug, question) VALUES (%s, %s) ON CONFLICT (slug) DO NOTHING RETURNING id",
            (DEMO_SLUG, DEMO_QUESTION),
        ).fetchone()
        if row is None:
            return False
        for position, label in enumerate(DEMO_OPTIONS, start=1):
            conn.execute(
                "INSERT INTO options (poll_id, position, label) VALUES (%s, %s, %s)", (row[0], position, label)
            )
        return True


def run(conninfo: str, migrations_dir: Path = MIGRATIONS_DIR, out: Callable[[str], None] = print) -> int:
    """Apply pending migrations; return how many were applied."""
    with psycopg.connect(conninfo, autocommit=True) as conn:
        conn.execute("SELECT pg_advisory_lock(%s)", (LOCK_ID,))
        try:
            conn.execute(
                "CREATE TABLE IF NOT EXISTS schema_migrations ("
                "version varchar(50) PRIMARY KEY, applied_at timestamptz NOT NULL)"
            )
            applied = {row[0] for row in conn.execute("SELECT version FROM schema_migrations")}
            count = 0
            for path in sorted(migrations_dir.glob("[0-9][0-9][0-9]_*.sql")):
                if path.stem in applied:
                    continue
                with conn.transaction():
                    conn.execute(path.read_text(encoding="utf-8"))
                    conn.execute(
                        "INSERT INTO schema_migrations (version, applied_at) VALUES (%s, now())", (path.stem,)
                    )
                out(f"applied {path.stem}")
                count += 1
            seeded = seed_demo(conn)
            out(f"{count} migration(s) applied" + ("; demo poll seeded" if seeded else ""))
            return count
        finally:
            conn.execute("SELECT pg_advisory_unlock(%s)", (LOCK_ID,))


def main() -> int:
    settings = load_settings()
    try:
        run(settings.conninfo(connect_timeout=10))
    except psycopg.Error as exc:
        print(f"migration failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
