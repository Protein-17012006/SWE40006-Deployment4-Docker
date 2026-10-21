"""Text drawing of the board and the leaderboard."""

import re

from .board import COLS, CPU, EMPTY, PLAYER, ROWS, Board

RED = "\x1b[1;31m"
YELLOW = "\x1b[1;33m"
RESET = "\x1b[0m"
_ANSI = re.compile(r"\x1b\[[0-9;]*m")


def strip_ansi(text: str) -> str:
    return _ANSI.sub("", text)


def render_board(board: Board, color: bool = True) -> str:
    """Draw the board with column numbers on top. Pieces stay readable as X and O without colour."""
    lines = ["  " + "   ".join(str(col + 1) for col in range(COLS))]
    for row in range(ROWS - 1, -1, -1):
        cells = []
        for col in range(COLS):
            piece = board.at(row, col)
            if color and piece == PLAYER:
                cells.append(f"{RED}X{RESET}")
            elif color and piece == CPU:
                cells.append(f"{YELLOW}O{RESET}")
            else:
                cells.append(piece if piece != EMPTY else ".")
        lines.append("| " + " | ".join(cells) + " |")
    lines.append("+" + "---+" * COLS)
    return "\n".join(lines) + "\n"


def render_standings(standings) -> str:
    """Leaderboard table; `standings` is a list of scores.Standing."""
    if not standings:
        return "No games recorded yet.\n"
    lines = [" #  Name              Score   W   L   D  Fastest win"]
    for s in standings:
        fastest = f"{s.fastest} moves" if s.fastest is not None else "-"
        lines.append(f"{s.rank:>2}  {s.name:<16}  {s.score:>5}  {s.wins:>2}  {s.losses:>2}  {s.draws:>2}  {fastest}")
    return "\n".join(lines) + "\n"
