"""CSRF double-submit token and the anonymous voter id cookie."""

import secrets
import uuid

CSRF_COOKIE = "qp_csrf"
CSRF_FIELD = "csrf_token"
VOTER_COOKIE = "qp_voter"
VOTER_MAX_AGE = 365 * 24 * 3600


def new_csrf_token() -> str:
    return secrets.token_urlsafe(32)


def looks_like_token(value: str | None) -> bool:
    return bool(value) and 20 <= len(value) <= 64 and value.isascii()


def csrf_valid(cookie_value: str | None, form_value: object) -> bool:
    """The form field must repeat the cookie. A cross-site form cannot read the cookie to copy it."""
    if not looks_like_token(cookie_value) or not isinstance(form_value, str) or not form_value.isascii():
        return False
    return secrets.compare_digest(cookie_value.encode(), form_value.encode())


def parse_voter_id(cookie_value: str | None) -> uuid.UUID | None:
    if not cookie_value:
        return None
    try:
        return uuid.UUID(cookie_value)
    except ValueError:
        return None
