import pytest

from connect4.board import COLS, CPU, EMPTY, PLAYER, ROWS, WINDOWS, Board, ColumnFull


def test_new_board_is_empty_and_every_column_is_legal():
    board = Board()
    assert all(cell == EMPTY for cell in board.cells)
    assert board.legal_moves() == list(range(COLS))
    assert board.winner() is None
    assert not board.is_full()


def test_pieces_stack_from_the_bottom():
    board = Board()
    assert board.drop(3, PLAYER) == 0
    assert board.drop(3, CPU) == 1
    assert board.at(0, 3) == PLAYER
    assert board.at(1, 3) == CPU


def test_full_column_is_rejected_and_not_legal():
    board = Board()
    for i in range(ROWS):
        board.drop(0, PLAYER if i % 2 == 0 else CPU)
    with pytest.raises(ColumnFull):
        board.drop(0, PLAYER)
    assert 0 not in board.legal_moves()
    assert not board.can_drop(0)


def test_column_outside_the_board_is_rejected():
    with pytest.raises(ValueError):
        Board().drop(7, PLAYER)
    with pytest.raises(ValueError):
        Board().drop(-1, PLAYER)


def test_undo_restores_the_cell_and_height():
    board = Board()
    row = board.drop(2, PLAYER)
    board.undo(row, 2)
    assert board.at(0, 2) == EMPTY
    assert board.heights[2] == 0


def test_there_are_69_windows_of_four():
    assert len(WINDOWS) == 69


@pytest.mark.parametrize(
    ("moves", "last_col"),
    [
        ("1122334", 4),          # horizontal on the bottom row
        ("1212121", 1),          # vertical in column 1
        ("12234334544", 4),      # diagonal up-right: (0,0) (1,1) (2,2) (3,3)
        ("76654554344", 4),      # diagonal up-left:  (0,6) (1,5) (2,4) (3,3)
    ],
)
def test_four_in_a_row_wins(moves, last_col):
    board = Board.from_moves(moves[:-1])
    assert board.winner() is None
    row = board.drop(last_col - 1, PLAYER)
    assert board.wins_at(row, last_col - 1)
    assert board.winner() == PLAYER


def test_no_false_win_across_a_row_boundary():
    # X on the last three cells of row 0 and the first cell of row 1: adjacent in the
    # flat list (indexes 4, 5, 6, 7) but not four in a row on the board.
    board = Board()
    for col in (4, 5, 6):
        board.drop(col, PLAYER)
    board.drop(0, CPU)            # row 0, col 0
    row = board.drop(0, PLAYER)   # row 1, col 0 -> flat index 7
    assert not board.wins_at(row, 0)
    assert board.winner() is None


def test_three_in_a_row_is_not_a_win():
    board = Board.from_moves("11223")
    assert board.winner() is None


def test_full_board_without_winner_is_a_draw():
    # Columns filled in pairs XXOOXX / OOXXOO patterns never make four in a row.
    pattern = ["XXOOXX", "OOXXOO", "XXOOXX", "OOXXOO", "XXOOXX", "OOXXOO", "XXOOXX"]
    board = Board()
    for col, column in enumerate(pattern):
        for piece in column:
            board.drop(col, piece)
    assert board.is_full()
    assert board.legal_moves() == []
    assert board.winner() is None
