import random
import time

import pytest

from connect4.ai import LEVELS, choose_move
from connect4.board import CPU, PLAYER, ROWS, Board


@pytest.mark.parametrize("level", [2, 3])
def test_takes_an_immediate_win(level):
    board = Board()
    for col in (0, 1, 2):
        board.drop(col, CPU)        # O O O . on the bottom row
    board.drop(0, PLAYER)
    board.drop(1, PLAYER)
    assert choose_move(board, level, random.Random(1)) == 3


@pytest.mark.parametrize("level", [2, 3])
def test_blocks_the_opponents_immediate_win(level):
    board = Board()
    for col in (0, 1, 2):
        board.drop(col, PLAYER)     # X X X . on the bottom row
    board.drop(6, CPU)
    board.drop(6, CPU)
    assert choose_move(board, level, random.Random(1)) == 3


def test_prefers_winning_over_blocking():
    board = Board()
    for col in (0, 1, 2):
        board.drop(col, PLAYER)     # X can win in column 4 ...
    for _ in range(3):
        board.drop(6, CPU)          # ... but O wins first in column 7
    assert choose_move(board, 2, random.Random(1)) == 6


@pytest.mark.parametrize("level", [1, 2, 3])
def test_only_returns_legal_moves(level):
    board = Board()
    for col in range(6):            # fill columns 1-6, leave column 7 open
        for row in range(ROWS):
            board.drop(col, PLAYER if (row // 2 + col) % 2 == 0 else CPU)
    for seed in range(20):
        assert choose_move(board, level, random.Random(seed)) == 6


def test_full_board_raises():
    board = Board()
    for col in range(7):
        for row in range(ROWS):
            board.drop(col, PLAYER if (row // 2 + col) % 2 == 0 else CPU)
    with pytest.raises(ValueError):
        choose_move(board, 2, random.Random(1))


@pytest.mark.parametrize("level", [1, 2, 3])
def test_is_deterministic_for_a_seed(level):
    board = Board.from_moves("4453")
    first = [choose_move(board, level, random.Random(seed)) for seed in range(10)]
    second = [choose_move(board, level, random.Random(seed)) for seed in range(10)]
    assert first == second


def test_does_not_change_the_board():
    board = Board.from_moves("4453")
    before = list(board.cells), list(board.heights)
    choose_move(board, 3, random.Random(1))
    assert (board.cells, board.heights) == before


def test_hard_answers_on_the_empty_board_in_under_two_seconds():
    start = time.perf_counter()
    col = choose_move(Board(), 3, random.Random(1))
    assert time.perf_counter() - start < 2.0
    assert col == 3                 # the centre column is the best opening


def test_hard_answers_a_busy_middle_game_in_under_two_seconds():
    # The slowest position found while tuning the search (about 1 s before leaf caching).
    board = Board.from_moves("445362")
    start = time.perf_counter()
    choose_move(board, 3, random.Random(1))
    assert time.perf_counter() - start < 2.0


def test_levels_are_easy_normal_hard():
    assert [LEVELS[level][0] for level in (1, 2, 3)] == ["Easy", "Normal", "Hard"]
