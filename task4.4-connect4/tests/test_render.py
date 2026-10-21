from connect4.board import Board
from connect4.render import render_board, render_standings, strip_ansi
from connect4.scores import Standing


def test_empty_board_drawing():
    lines = render_board(Board(), color=False).splitlines()
    assert lines[0] == "  1   2   3   4   5   6   7"
    assert lines[1] == "| . | . | . | . | . | . | . |"
    assert lines[-1] == "+---+---+---+---+---+---+---+"
    assert len(lines) == 8


def test_pieces_are_drawn_bottom_up_and_colour_only_wraps_them():
    board = Board.from_moves("44")
    plain = render_board(board, color=False)
    coloured = render_board(board, color=True)
    assert plain.splitlines()[-2] == "| . | . | . | X | . | . | . |"
    assert plain.splitlines()[-3] == "| . | . | . | O | . | . | . |"
    assert "\x1b[" in coloured
    assert strip_ansi(coloured) == plain


def test_standings_table_and_empty_message():
    assert render_standings([]) == "No games recorded yet.\n"
    table = render_standings([Standing(1, "Hoàng", 9, 3, 1, 0, 7), Standing(2, "Ana", 1, 1, 0, 2, None)])
    lines = table.splitlines()
    assert lines[0].startswith(" #  Name")
    assert lines[1].startswith(" 1  Hoàng")
    assert lines[1].endswith("7 moves")
    assert lines[2].endswith("-")
