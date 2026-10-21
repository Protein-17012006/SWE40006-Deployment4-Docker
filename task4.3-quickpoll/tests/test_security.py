import uuid

from quickpoll.security import csrf_valid, looks_like_token, new_csrf_token, parse_voter_id


def test_new_tokens_are_random_and_well_formed():
    first, second = new_csrf_token(), new_csrf_token()
    assert first != second
    assert looks_like_token(first) and looks_like_token(second)


def test_the_form_must_repeat_the_cookie():
    token = new_csrf_token()
    assert csrf_valid(token, token)
    assert not csrf_valid(token, new_csrf_token())


def test_missing_short_or_odd_tokens_are_rejected():
    token = new_csrf_token()
    assert not csrf_valid(None, token)
    assert not csrf_valid(token, None)
    assert not csrf_valid(token, ["a", "list"])
    assert not csrf_valid("short", "short")
    assert not csrf_valid(token, "ünïcødé" * 4)      # non-ASCII never reaches compare_digest


def test_voter_ids_must_be_uuids():
    voter = uuid.uuid4()
    assert parse_voter_id(str(voter)) == voter
    assert parse_voter_id("not-a-uuid") is None
    assert parse_voter_id("") is None
    assert parse_voter_id(None) is None
