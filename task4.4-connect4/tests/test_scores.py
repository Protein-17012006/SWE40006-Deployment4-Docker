from datetime import datetime, timezone

import pytest

from connect4.scores import ScoreStore


@pytest.fixture
def store(tmp_path):
    s = ScoreStore(tmp_path / "data" / "scores.db")
    yield s
    s.close()


def test_score_is_the_level_of_each_win(store):
    store.record("Ana", 3, "win", 9)      # 3 points
    store.record("Ana", 1, "win", 5)      # 1 point
    store.record("Ana", 2, "loss", 12)
    store.record("Bao", 2, "win", 8)      # 2 points
    store.record("Bao", 2, "draw", 21)
    top = store.top()
    assert [(s.name, s.score, s.wins, s.losses, s.draws) for s in top] == [("Ana", 4, 2, 1, 0), ("Bao", 2, 1, 0, 1)]
    assert [s.rank for s in top] == [1, 2]
    assert top[0].fastest == 5


def test_ties_break_on_fewer_losses_then_name(store):
    store.record("Cy", 2, "win", 9)
    store.record("Cy", 2, "loss", 9)
    store.record("Bo", 2, "win", 9)
    store.record("Al", 2, "win", 9)
    assert [s.name for s in store.top()] == ["Al", "Bo", "Cy"]


def test_player_without_wins_has_no_fastest(store):
    store.record("Dan", 1, "loss", 4)
    assert store.top()[0].fastest is None
    assert store.top()[0].score == 0


def test_limit_and_unknown_outcome(store):
    for i in range(12):
        store.record(f"P{i:02}", 1, "win", 10)
    assert len(store.top()) == 10
    assert len(store.top(5)) == 5
    with pytest.raises(ValueError):
        store.record("X", 1, "forfeit", 3)


def test_results_survive_reopening_the_file(tmp_path):
    path = tmp_path / "scores.db"
    first = ScoreStore(path)
    first.record("Hoàng", 3, "win", 11, datetime(2026, 10, 3, tzinfo=timezone.utc))
    first.close()
    second = ScoreStore(path)
    assert second.top()[0].name == "Hoàng"
    second.close()
