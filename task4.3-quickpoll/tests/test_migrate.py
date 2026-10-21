"""Migration runner tests against a real PostgreSQL. Skipped without TEST_DATABASE_URL."""

import os

import psycopg
import pytest

from quickpoll import migrate

DB_URL = os.environ.get("TEST_DATABASE_URL")
pytestmark = [
    pytest.mark.db,
    pytest.mark.skipif(not DB_URL, reason="TEST_DATABASE_URL is not set (run through compose.test.yaml)"),
]


@pytest.fixture(autouse=True)
def empty_schema():
    with psycopg.connect(DB_URL, autocommit=True) as conn:
        conn.execute("DROP SCHEMA public CASCADE")
        conn.execute("CREATE SCHEMA public")


def test_applies_every_migration_once_and_seeds_the_demo_poll():
    lines = []
    files = sorted(migrate.MIGRATIONS_DIR.glob("[0-9][0-9][0-9]_*.sql"))
    assert migrate.run(DB_URL, out=lines.append) == len(files)
    assert lines[-1] == f"{len(files)} migration(s) applied; demo poll seeded"

    again = []
    assert migrate.run(DB_URL, out=again.append) == 0
    assert again == ["0 migration(s) applied"]

    with psycopg.connect(DB_URL) as conn:
        versions = [row[0] for row in conn.execute("SELECT version FROM schema_migrations ORDER BY version")]
        demo = conn.execute(
            "SELECT p.question, count(o.id) FROM polls p JOIN options o ON o.poll_id = p.id "
            "WHERE p.slug = %s GROUP BY p.question", (migrate.DEMO_SLUG,)
        ).fetchone()
    assert versions == [f.stem for f in files]
    assert demo == (migrate.DEMO_QUESTION, len(migrate.DEMO_OPTIONS))


def test_a_failing_migration_is_rolled_back(tmp_path):
    (tmp_path / "001_ok.sql").write_text("CREATE TABLE ok_table (id int);", encoding="utf-8")
    (tmp_path / "002_broken.sql").write_text("CREATE TABLE broken (id int); SELECT * FROM missing_table;",
                                             encoding="utf-8")
    with pytest.raises(psycopg.errors.UndefinedTable):
        migrate.run(DB_URL, migrations_dir=tmp_path, out=lambda line: None)
    with psycopg.connect(DB_URL) as conn:
        tables = {row[0] for row in conn.execute(
            "SELECT tablename FROM pg_tables WHERE schemaname = 'public'")}
        versions = [row[0] for row in conn.execute("SELECT version FROM schema_migrations")]
    assert "ok_table" in tables and "broken" not in tables
    assert versions == ["001_ok"]
