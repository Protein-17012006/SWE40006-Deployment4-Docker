import pytest

from quickpoll.validation import clean_text, parse_option_id, validate_poll


def test_valid_poll_is_trimmed_and_kept_in_order():
    result = validate_poll("  Which runtime?  ", [" Docker ", "Podman", "", "  "])
    assert result.ok
    assert result.question == "Which runtime?"
    assert result.options == ["Docker", "Podman"]       # blank fields are dropped


@pytest.mark.parametrize("question", ["", "Why?", "x" * 201])
def test_question_length_is_5_to_200(question):
    assert "question" in validate_poll(question, ["a", "b"]).errors


def test_question_boundaries_are_accepted():
    assert validate_poll("x" * 5, ["a", "b"]).ok
    assert validate_poll("x" * 200, ["a", "b"]).ok


@pytest.mark.parametrize("options", [[], ["only one"], ["a", "", "  "], [str(i) for i in range(7)]])
def test_two_to_six_options(options):
    assert validate_poll("Pick one please", options).errors["options"] == "Give between 2 and 6 options."


def test_option_length_limit():
    assert validate_poll("Pick one please", ["a", "b" * 80]).ok
    assert "at most 80" in validate_poll("Pick one please", ["a", "b" * 81]).errors["options"]


def test_duplicate_options_are_case_insensitive():
    assert validate_poll("Pick one please", ["Docker", "DOCKER"]).errors["options"] == "Each option must be different."


def test_vietnamese_text_is_accepted_and_normalised():
    result = validate_poll("Bạn thích gì nhất?", ["Phở", "Bu\u0301n chả"])   # second one is decomposed
    assert result.ok
    assert result.options[1] == "Bún chả"


def test_control_characters_are_removed():
    assert clean_text("Hello\x00 wor\x07ld\n") == "Hello world"


@pytest.mark.parametrize("value", [None, 42, ["a"], b"bytes"])
def test_non_string_input_counts_as_empty(value):
    assert clean_text(value) == ""
    assert not validate_poll(value, [value, value]).ok


@pytest.mark.parametrize(("value", "expected"), [("7", 7), ("123456", 123456), ("0", None), ("-1", None),
                                                  ("3.5", None), ("abc", None), ("", None), ("²", None),
                                                  ("1" * 19, None), (None, None), (["1"], None)])
def test_parse_option_id(value, expected):
    assert parse_option_id(value) == expected
