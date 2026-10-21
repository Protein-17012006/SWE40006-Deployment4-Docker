"""The Connect Four dialogue as a state machine with no I/O of its own.

`play` (local console) and `serve` (TCP) both feed it input lines and print what it returns.
"""

import random
import socket
import unicodedata
from typing import Callable

from .ai import LEVELS, choose_move
from .board import CPU, PLAYER, Board, ColumnFull
from .render import render_board, render_standings

NAME_MAX = 16
HELP = (
    "How to play: type a column number 1-7 and press Enter to drop your X.\n"
    "Get four in a row - across, up or diagonally - before the CPU does.\n"
    "Commands: h = help, q = quit.\n"
)

ResultCallback = Callable[[str, int, str, int], None]


def clean_name(text: str) -> str | None:
    """NFC-normalise and trim; allow letters and digits in any script, space, '_' and '-'."""
    name = unicodedata.normalize("NFC", text).strip()
    if not 1 <= len(name) <= NAME_MAX:
        return None
    if all(ch.isalnum() or ch in " _-" for ch in name):
        return name
    return None


class GameSession:
    def __init__(self, scores=None, rng: random.Random | None = None, color: bool = True,
                 host: str | None = None, on_result: ResultCallback | None = None) -> None:
        self.scores = scores
        self.rng = rng or random.Random()
        self.color = color
        self.host = host or socket.gethostname()
        self.on_result = on_result
        self.state = "name"
        self.name = ""
        self.level = 2
        self.board = Board()
        self.moves = 0

    @property
    def finished(self) -> bool:
        return self.state == "done"

    def start(self) -> str:
        return (
            f"CONNECT FOUR - SWE40006 Task 4.4 - host {self.host}\n"
            "Drop discs into columns 1-7 and connect four in a row to win.\n"
            + self._prompt()
        )

    def handle(self, line: str) -> str:
        if self.finished:
            return ""
        text = line.strip()
        if text.lower() == "q":
            return self._quit()
        if text.lower() == "h":
            return HELP + self._prompt()
        return getattr(self, f"_on_{self.state}")(text)

    def _prompt(self) -> str:
        return {
            "name": f"Your name (1-{NAME_MAX} letters or digits): ",
            "level": "Choose a level - 1 Easy, 2 Normal, 3 Hard: ",
            "move": "Your move (1-7, h = help, q = quit): ",
            "again": "Play again? (y/n): ",
        }[self.state]

    def _on_name(self, text: str) -> str:
        name = clean_name(text)
        if name is None:
            return f"Names use 1-{NAME_MAX} letters, digits, spaces, '_' or '-'.\n" + self._prompt()
        self.name = name
        self.state = "level"
        return f"Hello, {name}!\n" + self._prompt()

    def _on_level(self, text: str) -> str:
        if text not in ("1", "2", "3"):
            return "Please type 1, 2 or 3.\n" + self._prompt()
        self.level = int(text)
        self.board = Board()
        self.moves = 0
        self.state = "move"
        return (
            f"\nLevel: {LEVELS[self.level][0]}. You are X (red) and move first.\n"
            + render_board(self.board, self.color)
            + self._prompt()
        )

    def _on_move(self, text: str) -> str:
        if len(text) != 1 or text not in "1234567":
            return "Type a column number from 1 to 7.\n" + self._prompt()
        col = int(text) - 1
        try:
            row = self.board.drop(col, PLAYER)
        except ColumnFull:
            return f"Column {col + 1} is full. Choose another.\n" + self._prompt()
        self.moves += 1
        if self.board.wins_at(row, col):
            return render_board(self.board, self.color) + self._finish("win", f"You win in {self.moves} moves!")
        if self.board.is_full():
            return render_board(self.board, self.color) + self._finish("draw", "Draw - the board is full.")
        cpu_col = choose_move(self.board, self.level, self.rng)
        cpu_row = self.board.drop(cpu_col, CPU)
        out = f"You drop in column {col + 1}. CPU drops in column {cpu_col + 1}.\n" + render_board(self.board, self.color)
        if self.board.wins_at(cpu_row, cpu_col):
            return out + self._finish("loss", "The CPU wins. Better luck next time!")
        if self.board.is_full():
            return out + self._finish("draw", "Draw - the board is full.")
        return out + self._prompt()

    def _finish(self, outcome: str, message: str) -> str:
        if self.scores is not None:
            self.scores.record(self.name, self.level, outcome, self.moves)
        if self.on_result is not None:
            self.on_result(self.name, self.level, outcome, self.moves)
        self.state = "again"
        table = ""
        if self.scores is not None:
            table = "\nTop players:\n" + render_standings(self.scores.top(5))
        return f"{message}\n{table}\n" + self._prompt()

    def _on_again(self, text: str) -> str:
        answer = text.lower()
        if answer in ("y", "yes"):
            self.state = "level"
            return self._prompt()
        if answer in ("n", "no"):
            return self._quit()
        return "Please answer y or n.\n" + self._prompt()

    def _quit(self) -> str:
        self.state = "done"
        who = f", {self.name}" if self.name else ""
        return f"Thanks for playing{who}. Bye!\n"
