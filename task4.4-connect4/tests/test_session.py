import random

import pytest

from connect4.board import COLS, CPU, PLAYER, ROWS, Board
from connect4.scores import ScoreStore
from connect4.session import GameSession, clean_name


@pytest.fixture
def store(tmp_path):
    s = ScoreStore(tmp_path / "scores.db")
    yield s
    s.close()


def new_session(store=None, results=None):
    return GameSession(
        scores=store,
        rng=random.Random(1),
        color=False,
        host="test-host",
        on_result=(lambda *r: results.append(r)) if results is not None else None,
    )


def at_move(session, board):
    """Put a session straight into the 'move' state with a prepared board (player X to move)."""
    session.name, session.level, session.state = "Ana", 2, "move"
    session.board = board
    return session


def test_start_shows_banner_then_name_prompt():
    text = new_session().start()
    assert text.splitlines()[0] == "CONNECT FOUR - SWE40006 Task 4.4 - host test-host"
    assert text.endswith("Your name (1-16 letters or digits): ")


@pytest.mark.parametrize("bad", ["", "   ", "a" * 17, "bad!", "<script>", "tab\tname"])
def test_invalid_names_are_rejected(bad):
    session = new_session()
    reply = session.handle(bad)
    assert reply.startswith("Names use 1-16 letters")
    assert session.state == "name"


def test_vietnamese_name_is_accepted_and_normalised():
    session = new_session()
    reply = session.handle("Hoa\u0300ng")          # decomposed: a + combining grave
    assert session.name == "Hoàng"                # stored composed (NFC)
    assert reply.startswith("Hello, Hoàng!")
    assert clean_name("  Huy-Hoang_1 ") == "Huy-Hoang_1"


def test_level_must_be_1_2_or_3():
    session = new_session()
    session.handle("Ana")
    assert session.handle("4").startswith("Please type 1, 2 or 3.")
    reply = session.handle("3")
    assert "Level: Hard. You are X (red) and move first." in reply
    assert reply.endswith("Your move (1-7, h = help, q = quit): ")


@pytest.mark.parametrize("bad", ["0", "8", "abc", "", "44", "-1"])
def test_invalid_moves_are_rejected(bad):
    session = at_move(new_session(), Board())
    assert session.handle(bad).startswith("Type a column number from 1 to 7.")
    assert session.board.legal_moves() == list(range(COLS))


def test_full_column_is_rejected():
    board = Board()
    for i in range(ROWS):
        board.drop(0, PLAYER if (i // 2) % 2 == 0 else CPU)
    session = at_move(new_session(), board)
    assert session.handle("1").startswith("Column 1 is full.")


def test_a_move_gets_a_cpu_reply_and_a_new_prompt():
    session = at_move(new_session(), Board())
    reply = session.handle("4")
    assert reply.startswith("You drop in column 4. CPU drops in column ")
    assert reply.endswith("Your move (1-7, h = help, q = quit): ")
    assert sum(session.board.heights) == 2


def test_player_win_is_recorded_and_offers_another_game(store):
    results = []
    session = at_move(new_session(store, results), Board.from_moves("152535"))  # X X X . / O stacked in col 5
    session.moves = 3
    reply = session.handle("4")
    assert "You win in 4 moves!" in reply
    assert "Top players:" in reply and " 1  Ana" in reply
    assert reply.endswith("Play again? (y/n): ")
    assert results == [("Ana", 2, "win", 4)]
    assert store.top()[0].wins == 1


def test_cpu_win_is_recorded_as_a_loss(store):
    results = []
    session = at_move(new_session(store, results), Board.from_moves("171727"))  # O has three in column 7
    reply = session.handle("3")
    assert "CPU drops in column 7." in reply
    assert "The CPU wins. Better luck next time!" in reply
    assert results[0][2] == "loss"


def test_last_free_cell_without_four_is_a_draw():
    board = Board()
    for col in range(COLS):
        for row in range(ROWS):
            if (row, col) != (ROWS - 1, COLS - 1):
                board.drop(col, PLAYER if (row // 2 + col) % 2 == 0 else CPU)
    results = []
    session = at_move(new_session(results=results), board)
    reply = session.handle("7")
    assert "Draw - the board is full." in reply
    assert results[0][2] == "draw"
    assert "Top players:" not in reply             # no score store in this session


def test_play_again_flow():
    session = at_move(new_session(), Board.from_moves("152535"))
    session.handle("4")
    assert session.handle("maybe").startswith("Please answer y or n.")
    assert session.handle("y") == "Choose a level - 1 Easy, 2 Normal, 3 Hard: "
    assert "Level: Easy" in session.handle("1")
    assert session.board.legal_moves() == list(range(COLS))   # a fresh board


def test_no_ends_the_session():
    session = at_move(new_session(), Board.from_moves("152535"))
    session.handle("4")
    assert session.handle("n") == "Thanks for playing, Ana. Bye!\n"
    assert session.finished
    assert session.handle("4") == ""


def test_help_and_quit_work_in_every_state():
    session = new_session()
    assert session.handle("h").startswith("How to play:")
    assert session.handle("h").endswith("Your name (1-16 letters or digits): ")
    assert session.handle("Q") == "Thanks for playing. Bye!\n"
    assert session.finished
