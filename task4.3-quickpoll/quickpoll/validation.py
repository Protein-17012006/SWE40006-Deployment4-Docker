"""Pure validation of user input. Never raises on malformed input: it reports errors instead."""

import unicodedata
from dataclasses import dataclass, field
from datetime import timedelta

QUESTION_MIN, QUESTION_MAX = 5, 200
OPTION_MAX = 80
OPTIONS_MIN, OPTIONS_MAX = 2, 6
CLOSE_AFTER = {"never": None, "1h": timedelta(hours=1), "1d": timedelta(days=1), "7d": timedelta(days=7)}


def clean_text(value: object) -> str:
    """NFC-normalise, drop control characters and trim. Anything that is not a string becomes ''."""
    if not isinstance(value, str):
        return ""
    value = unicodedata.normalize("NFC", value)
    return "".join(ch for ch in value if unicodedata.category(ch) != "Cc").strip()


@dataclass
class PollInput:
    question: str
    options: list[str]
    errors: dict[str, str] = field(default_factory=dict)
    close_after: str = "never"

    @property
    def ok(self) -> bool:
        return not self.errors


def validate_poll(question: object, options: list[object], close_after: object = "never") -> PollInput:
    q = clean_text(question)
    opts = [o for o in (clean_text(v) for v in options) if o]
    errors: dict[str, str] = {}
    if not QUESTION_MIN <= len(q) <= QUESTION_MAX:
        errors["question"] = f"The question needs {QUESTION_MIN} to {QUESTION_MAX} characters."
    if not OPTIONS_MIN <= len(opts) <= OPTIONS_MAX:
        errors["options"] = f"Give between {OPTIONS_MIN} and {OPTIONS_MAX} options."
    elif any(len(o) > OPTION_MAX for o in opts):
        errors["options"] = f"Each option can have at most {OPTION_MAX} characters."
    elif len({o.casefold() for o in opts}) != len(opts):
        errors["options"] = "Each option must be different."
    if not isinstance(close_after, str) or close_after not in CLOSE_AFTER:
        errors["close_after"] = "Choose when the poll closes."
        close_after = "never"
    return PollInput(q, opts, errors, close_after)


def parse_option_id(value: object) -> int | None:
    """A positive integer id sent by the vote form, or None for anything else."""
    if isinstance(value, str) and value.isascii() and value.isdigit() and 0 < len(value) <= 18:
        number = int(value)
        return number if number > 0 else None
    return None
