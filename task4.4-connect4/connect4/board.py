"""Connect Four rules on a 6 x 7 board.

Cells are stored in a flat list, index = row * COLS + col, with row 0 at the BOTTOM.
Columns are 0-based here; the user interface shows them as 1-7.
"""

ROWS = 6
COLS = 7
EMPTY = "."
PLAYER = "X"
CPU = "O"

_DIRECTIONS = ((0, 1), (1, 0), (1, 1), (1, -1))


def _windows() -> tuple[tuple[int, ...], ...]:
    """Every line of four cells on the board (69 of them), as flat indexes."""
    found = []
    for row in range(ROWS):
        for col in range(COLS):
            for dr, dc in _DIRECTIONS:
                end_row, end_col = row + 3 * dr, col + 3 * dc
                if 0 <= end_row < ROWS and 0 <= end_col < COLS:
                    found.append(tuple((row + i * dr) * COLS + (col + i * dc) for i in range(4)))
    return tuple(found)


WINDOWS = _windows()


class ColumnFull(ValueError):
    """The chosen column has no free cell."""


class Board:
    __slots__ = ("cells", "heights")

    def __init__(self) -> None:
        self.cells = [EMPTY] * (ROWS * COLS)
        self.heights = [0] * COLS

    @classmethod
    def from_moves(cls, moves: str) -> "Board":
        """Build a position from 1-based columns, X moving first: "4455" is X4, O4, X5, O5."""
        board = cls()
        for turn, ch in enumerate(moves):
            board.drop(int(ch) - 1, PLAYER if turn % 2 == 0 else CPU)
        return board

    def at(self, row: int, col: int) -> str:
        return self.cells[row * COLS + col]

    def can_drop(self, col: int) -> bool:
        return 0 <= col < COLS and self.heights[col] < ROWS

    def legal_moves(self) -> list[int]:
        return [col for col in range(COLS) if self.heights[col] < ROWS]

    def drop(self, col: int, piece: str) -> int:
        """Drop a piece into a column and return the row it landed on."""
        if not 0 <= col < COLS:
            raise ValueError(f"column {col} is outside the board")
        row = self.heights[col]
        if row >= ROWS:
            raise ColumnFull(f"column {col + 1} is full")
        self.cells[row * COLS + col] = piece
        self.heights[col] = row + 1
        return row

    def undo(self, row: int, col: int) -> None:
        self.cells[row * COLS + col] = EMPTY
        self.heights[col] = row

    def wins_at(self, row: int, col: int) -> bool:
        """True if the piece at (row, col) is part of four in a row."""
        piece = self.cells[row * COLS + col]
        if piece == EMPTY:
            return False
        for dr, dc in _DIRECTIONS:
            count = 1
            for sign in (1, -1):
                r, c = row + dr * sign, col + dc * sign
                while 0 <= r < ROWS and 0 <= c < COLS and self.cells[r * COLS + c] == piece:
                    count += 1
                    r += dr * sign
                    c += dc * sign
            if count >= 4:
                return True
        return False

    def winner(self) -> str | None:
        for window in WINDOWS:
            first = self.cells[window[0]]
            if first != EMPTY and all(self.cells[i] == first for i in window[1:]):
                return first
        return None

    def is_full(self) -> bool:
        return all(height == ROWS for height in self.heights)
