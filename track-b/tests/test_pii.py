# Unit tests for the rule-based PII detector and the two redaction functions
# (issue #43, ADR-0008). Pure functions, so nothing needs to be running.

import pytest
from regdocs_track_b.pii import (
    detect_pii,
    luhn_valid,
    mod97_valid,
    ppsn_valid,
    redact_answer,
    redact_query,
)


def _found(text):
    found = []
    for match in detect_pii(text):
        found.append((match.kind, match.text))
    return found


def test_an_email_address_is_detected():
    assert _found("Write to jane.doe@example.ie about it") == [
        ("EMAIL", "jane.doe@example.ie")
    ]


@pytest.mark.parametrize(
    "number",
    ["087 123 4567", "087-123-4567", "0871234567", "+353 87 123 4567", "(01) 234 5678"],
)
def test_irish_phone_numbers_are_detected(number):
    assert _found(f"Call me on {number} please") == [("PHONE", number)]


def test_an_iban_is_detected_as_one_match_not_also_as_a_phone_or_card():
    assert _found("Refund to IE29 AIBK 9311 5212 3456 78 today") == [
        ("IBAN", "IE29 AIBK 9311 5212 3456 78")
    ]


def test_a_card_number_that_passes_the_luhn_check_is_detected():
    assert _found("My card is 4111 1111 1111 1111.") == [
        ("CARD", "4111 1111 1111 1111")
    ]


def test_a_long_number_that_fails_the_luhn_check_is_not_a_card():
    assert _found("Reference 1234 5678 9012 3456 was rejected") == []


@pytest.mark.parametrize("ppsn", ["1234567T", "1234567TW", "7654321PA"])
def test_a_ppsn_is_detected(ppsn):
    assert _found(f"My PPSN is {ppsn}") == [("PPSN", ppsn)]


def test_a_ppsn_with_the_wrong_check_letter_is_not_detected():
    assert _found("Reference 1234567A was filed") == []


def test_a_reference_number_with_leading_zeros_is_not_a_phone_number():
    assert _found("See reference 0001234567 for details") == []


def test_ordinary_regulatory_text_raises_nothing():
    text = "Under CP54 section 3.12, a firm must give 30 days' notice by 05 01 2024."

    assert _found(text) == []


def test_several_kinds_are_returned_in_the_order_they_appear():
    text = "Email jane@x.ie or call 087 123 4567"

    assert _found(text) == [("EMAIL", "jane@x.ie"), ("PHONE", "087 123 4567")]


def test_matches_carry_their_character_offsets():
    text = "Email jane@x.ie now"
    (match,) = detect_pii(text)

    assert text[match.start : match.end] == "jane@x.ie"


def test_luhn_and_mod97_checksums():
    assert luhn_valid("4111111111111111")
    assert not luhn_valid("1234567890123456")
    assert mod97_valid("IE29AIBK93115212345678")
    assert not mod97_valid("IE30AIBK93115212345678")
    assert ppsn_valid("1234567T")
    assert ppsn_valid("1234567TW")
    assert ppsn_valid("7654321PA")
    assert not ppsn_valid("1234567A")


def test_redact_query_replaces_each_span_with_a_typed_placeholder():
    text = "Email jane@x.ie or call 087 123 4567"

    redacted = redact_query(text, detect_pii(text))

    assert redacted == "Email [REDACTED:EMAIL] or call [REDACTED:PHONE]"


def test_redact_query_with_no_matches_returns_the_text_unchanged():
    assert redact_query("How much notice?", []) == "How much notice?"


def test_redact_answer_replaces_every_echo_of_a_value_found_in_the_query():
    matches = detect_pii("My email is jane@x.ie")
    answer = "We will write to jane@x.ie. Replies to jane@x.ie are within 5 days."

    assert redact_answer(answer, matches) == (
        "We will write to [REDACTED:EMAIL]. "
        "Replies to [REDACTED:EMAIL] are within 5 days."
    )


def test_redact_answer_does_not_cut_into_a_longer_word_or_number():
    matches = detect_pii("My email is jane@x.ie")
    answer = "Not jane@x.ieee, but jane@x.ie is fine."

    assert redact_answer(answer, matches) == (
        "Not jane@x.ieee, but [REDACTED:EMAIL] is fine."
    )


def test_redact_answer_leaves_pii_the_query_did_not_contain_alone():
    matches = detect_pii("My email is jane@x.ie")
    answer = "Contact the Central Bank at info@centralbank.ie instead."

    assert redact_answer(answer, matches) == answer
