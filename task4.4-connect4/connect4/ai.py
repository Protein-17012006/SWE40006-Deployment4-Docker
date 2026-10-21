"""CPU player: minimax with alpha-beta pruning, searched centre-first."""

import math
import random

from .board import COLS, CPU, PLAYER, ROWS, WINDOWS, Board

# level -> (name, search depth, chance of a random move)
LEVELS = {
    1: ("Easy", 1, 0.3),
    2: ("Normal", 4, 0.0),
    3: ("Hard", 6, 0.0),
}

CENTRE_FIRST = (3, 2, 4, 1, 5, 0, 6)
WIN = 1_000_000
_CENTRE_CELLS = tuple(row * COLS + 3 for row in range(ROWS))


def evaluate(board: Board) -> int:
    """Heuristic score of a position from the CPU's point of view."""
    cells = board.cells
    score = 0
    for index in _CENTRE_CELLS:
        if cells[index] == CPU:
            score += 3
        elif cells[index] == PLAYER:
            score -= 3
    for window in WINDOWS:
        cpu = player = 0
        for index in window:
            value = cells[index]
            if value == CPU:
                cpu += 1
            elif value == PLAYER:
                player += 1
        if player == 0:
            if cpu == 3:
                score += 5
            elif cpu == 2:
                score += 2
        elif cpu == 0:
            if player == 3:
                score -= 5
            elif player == 2:
                score -= 2
    return score


def _search(board: Board, depth: int, alpha: float, beta: float, cpu_to_move: bool, cache: dict) -> float:
    moves = [col for col in CENTRE_FIRST if board.heights[col] < ROWS]
    if not moves:
        return 0  # draw
    if depth == 0:
        # The same position is reached through different move orders, so leaf scores are cached.
        key = "".join(board.cells)
        score = cache.get(key)
        if score is None:
            score = cache[key] = evaluate(board)
        return score
    if cpu_to_move:
        best = -math.inf
        for col in moves:
            row = board.drop(col, CPU)
            if board.wins_at(row, col):
                score = WIN + depth
            else:
                score = _search(board, depth - 1, alpha, beta, False, cache)
            board.undo(row, col)
            best = max(best, score)
            alpha = max(alpha, best)
            if alpha >= beta:
                break
        return best
    best = math.inf
    for col in moves:
        row = board.drop(col, PLAYER)
        if board.wins_at(row, col):
            score = -(WIN + depth)
        else:
            score = _search(board, depth - 1, alpha, beta, True, cache)
        board.undo(row, col)
        best = min(best, score)
        beta = min(beta, best)
        if alpha >= beta:
            break
    return best


def choose_move(board: Board, level: int, rng: random.Random) -> int:
    """Return the 0-based column the CPU plays. The board is left unchanged."""
    _, depth, randomness = LEVELS[level]
    moves = [col for col in CENTRE_FIRST if board.heights[col] < ROWS]
    if not moves:
        raise ValueError("no legal move: the board is full")
    if randomness and rng.random() < randomness:
        return rng.choice(moves)
    best_col, best_score = moves[0], -math.inf
    alpha, beta = -math.inf, math.inf
    cache: dict = {}
    for col in moves:
        row = board.drop(col, CPU)
        if board.wins_at(row, col):
            score = WIN + depth
        else:
            score = _search(board, depth - 1, alpha, beta, False, cache)
        board.undo(row, col)
        if score > best_score:
            best_col, best_score = col, score
        alpha = max(alpha, best_score)
    return best_col
