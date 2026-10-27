# The pure parts of verify (issue #47, ADR-0006, ADR-0035): reading the judge's
# per-claim lines, computing Confidence in code, and turning it into Flags.

import pytest
from regdocs_track_b.judge import (
    LOW_CONFIDENCE_THRESHOLD,
    confidence_of,
    flags_for,
    parse_verdicts,
)


def _supported_flags(verdicts):
    flags = []
    for verdict in verdicts:
        flags.append(verdict.supported)
    return flags


def test_each_claim_line_becomes_a_verdict():
    reply = (
        "SUPPORTED: Firms must give 30 days' notice.\n"
        "UNSUPPORTED: Fees are capped at 2%.\n"
    )

    verdicts = parse_verdicts(reply)

    assert _supported_flags(verdicts) == [True, False]
    assert verdicts[0].claim == "Firms must give 30 days' notice."


def test_unsupported_is_not_mistaken_for_supported():
    verdicts = parse_verdicts("UNSUPPORTED: A claim.")

    assert _supported_flags(verdicts) == [False]


def test_case_bullets_numbering_and_preamble_are_tolerated():
    reply = (
        "Here is my analysis:\n"
        "- supported: First claim.\n"
        "2. Unsupported: Second claim.\n"
        "Hope that helps!"
    )

    assert _supported_flags(parse_verdicts(reply)) == [True, False]


def test_a_reply_with_no_claim_lines_yields_no_verdicts():
    assert parse_verdicts("I think the answer is fine.") == []
    assert parse_verdicts("") == []


def test_confidence_is_the_fraction_of_claims_supported():
    verdicts = parse_verdicts(
        "SUPPORTED: a\nSUPPORTED: b\nUNSUPPORTED: c\nSUPPORTED: d"
    )

    assert confidence_of(verdicts) == 0.75


def test_no_verdicts_means_zero_confidence_not_a_division_error():
    assert confidence_of([]) == 0.0


@pytest.mark.parametrize(
    ("confidence", "expected"),
    [
        (1.0, []),
        (LOW_CONFIDENCE_THRESHOLD, []),
        (0.75, ["low_confidence"]),
        (0.01, ["low_confidence"]),
        (0.0, ["low_confidence", "no_supporting_context"]),
    ],
)
def test_flags_follow_the_threshold_and_zero_support(confidence, expected):
    assert flags_for(confidence) == expected
