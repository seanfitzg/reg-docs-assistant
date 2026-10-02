# Unit tests for the Gold Locator match rule (issue #30, ADR-0028): the
# pure function that decides whether a retrieved Chunk's locator counts as
# a hit for a Gold Locator. Written before match.py, red-green-refactor.
#
# The examples are real locator strings from ingestion/output/chunks/
# wherever the current chunkers produce them. The exception is child
# clauses like "3.12(a)": no chunker emits those yet, but ADR-0028 names
# them as exactly the finer-chunker case the rule has to survive.

import pytest

from match import case_hit, locator_matches

# ---- clause_numbered: compare by numbering segment, not string prefix ----


# @pytest.mark.parametrize runs the test once per tuple, unpacking each
# into the named arguments -- like NUnit's [TestCase("3.12", "3.12")].
@pytest.mark.parametrize(
    ("gold", "retrieved"),
    [
        ("3.12", "3.12"),  # the same clause
        ("3.12", "3.12(a)"),  # a child of the gold clause, from a finer chunker
        ("3.12", "3.12(a)(i)"),  # a grandchild is still inside 3.12
        ("3", "3.12"),  # a whole-chapter gold covers every clause in it
    ],
)
def test_clause_matches_itself_and_its_children(gold, retrieved):
    assert locator_matches(gold, retrieved, "clause_numbered")


@pytest.mark.parametrize(
    ("gold", "retrieved"),
    [
        ("3.1", "3.12"),  # the naive startswith() bug ADR-0028 exists to prevent
        ("3.1", "13.1"),  # a substring match, not a clause match
        ("3.12", "3.1"),  # the parent is not inside its child...
        ("3.12(a)", "3.12"),  # ...even one level up: 3.12 holds more than (a)
        ("3.12(a)", "3.12(b)"),
        ("1.1", "1.10"),  # real CP54 locators: 1.1 and 1.10 are siblings
    ],
)
def test_clause_does_not_match_a_different_clause(gold, retrieved):
    assert not locator_matches(gold, retrieved, "clause_numbered")


# ---- heading_sections / academic_sections: exact heading, page within ±1 ----


@pytest.mark.parametrize("strategy", ["heading_sections", "academic_sections"])
@pytest.mark.parametrize(
    ("gold", "retrieved", "expected"),
    [
        ("Introduction (p. 3)", "Introduction (p. 3)", True),
        (
            "Introduction (p. 3)",
            "Introduction (p. 4)",
            True,
        ),  # +1: a chunker that paginates differently
        ("Introduction (p. 3)", "Introduction (p. 2)", True),  # -1
        ("Introduction (p. 3)", "Introduction (p. 5)", False),  # +2: a different "Introduction"
        ("Introduction (p. 3)", "Introduction (p. 1)", False),  # -2
        ("Introduction (p. 3)", "Background (p. 3)", False),  # same page, different section
        ("Introduction (p. 3)", "introduction (p. 3)", False),  # exact means case-sensitive too
        # Real academic_sections locator, whose heading contains a number and
        # a colon -- only the trailing "(p. N)" is the page.
        ("Figure 1: Overview of soft data (p. 4)", "Figure 1: Overview of soft data (p. 4)", True),
        # Real heading_sections locator whose heading is itself in brackets:
        # "(4)" must be kept as the heading, not mistaken for locator syntax.
        ("(4) (p. 33)", "(4) (p. 34)", True),
        # A heading containing its own "(p. N)": the page is the LAST one,
        # so gold p. 33 vs retrieved p. 34 is within ±1 -- whereas reading
        # the first "(p. 2)" as the page would make the headings differ.
        ("Notes (p. 2) (p. 33)", "Notes (p. 2) (p. 34)", True),
        ("Notes (p. 2) (p. 33)", "Notes (p. 2) (p. 36)", False),
    ],
)
def test_heading_must_match_exactly_and_page_within_one(strategy, gold, retrieved, expected):
    assert locator_matches(gold, retrieved, strategy) is expected


def test_heading_whitespace_from_pdf_extraction_is_part_of_the_heading():
    # A real heading_sections locator keeps extraction's doubled space. Both
    # sides come from the same chunker, so exact comparison is still right;
    # this pins that the rule doesn't quietly normalise it away.
    gold = "Solvency  II - Implementation (p. 24)"
    assert locator_matches(gold, gold, "heading_sections")
    assert not locator_matches(gold, "Solvency II - Implementation (p. 24)", "heading_sections")


# ---- errors: fail loudly rather than score a silent miss ----


def test_unknown_strategy_raises():
    # pytest.raises is NUnit's Assert.Throws<ValueError>: the test fails
    # unless the "with" block raises that exception. match= is a regex
    # searched for in the exception's message. A "with" block runs setup
    # and guaranteed teardown around its body -- C#'s "using" statement.
    with pytest.raises(ValueError, match="unknown chunking strategy"):
        locator_matches("3.12", "3.12", "fixed_window")


@pytest.mark.parametrize(
    ("locator", "strategy"),
    [
        ("Introduction (p. 3)", "clause_numbered"),  # a heading locator under the clause rule
        ("3.12.", "clause_numbered"),
        ("", "clause_numbered"),
        ("3.12", "heading_sections"),  # a clause locator under the heading rule
        ("Introduction", "heading_sections"),  # no page
        ("Introduction (p. )", "academic_sections"),
        # Non-ASCII digits: Python's \d and int() would both accept this
        # Arabic-Indic "3", so the patterns spell out [0-9] instead.
        ("٣.12", "clause_numbered"),
        ("Introduction (p. ٣)", "heading_sections"),
    ],
)
def test_unparseable_gold_locator_raises(locator, strategy):
    with pytest.raises(ValueError, match="unparseable"):
        locator_matches(locator, locator, strategy)


def test_unparseable_retrieved_locator_raises():
    # Checked on both sides: a malformed retrieved locator is a chunker bug,
    # and a silent False would read as a retrieval miss.
    with pytest.raises(ValueError, match="unparseable"):
        locator_matches("3.12", "Introduction (p. 3)", "clause_numbered")


# ---- case_hit: any Gold Locator matching any retrieved Chunk ----

CP54 = "doc-04-cp54-second-consultation-consumer-protection-code"
CP47 = "doc-03-cp47-review-of-consumer-protection-code"


def _retrieved(document_id, locator, chunking_strategy):
    # The shape #32's retrieval query returns per Chunk (similarity aside).
    return {"document_id": document_id, "locator": locator, "chunking_strategy": chunking_strategy}


def test_case_is_a_hit_when_any_gold_locator_matches_any_retrieved_chunk():
    gold = [
        {"document_id": CP54, "locator": "1.1"},
        {"document_id": CP54, "locator": "3.12"},
    ]
    retrieved = [
        _retrieved(CP47, "Introduction (p. 3)", "heading_sections"),
        _retrieved(CP54, "3.12(a)", "clause_numbered"),  # matches the second gold only
    ]
    assert case_hit(gold, retrieved)


def test_case_is_a_miss_when_nothing_matches():
    gold = [{"document_id": CP54, "locator": "3.1"}]
    retrieved = [
        _retrieved(CP54, "3.12", "clause_numbered"),
        _retrieved(CP54, "13.1", "clause_numbered"),
    ]
    assert not case_hit(gold, retrieved)


def test_matching_locator_in_a_different_document_is_not_a_hit():
    # "1.1" exists in lots of Documents; only the gold Document's counts.
    gold = [{"document_id": CP54, "locator": "1.1"}]
    retrieved = [_retrieved("doc-01-cp01-funding-of-ifsra", "1.1", "clause_numbered")]
    assert not case_hit(gold, retrieved)


def test_other_documents_locators_are_never_parsed_against_the_gold():
    # A retrieved heading-section Chunk from another Document must not be
    # run through the clause rule (and raise) just because the gold is a
    # clause: comparison only happens within the same Document.
    gold = [{"document_id": CP54, "locator": "1.1"}]
    retrieved = [
        _retrieved(CP47, "Introduction (p. 3)", "heading_sections"),
        _retrieved(CP54, "1.1", "clause_numbered"),
    ]
    assert case_hit(gold, retrieved)


@pytest.mark.parametrize(
    "bad_chunk",
    [
        _retrieved(CP47, "Introduction (p. 3)", "fixed_window"),  # unknown strategy
        _retrieved(CP47, "Introduction", "heading_sections"),  # unparseable locator
    ],
)
def test_bad_retrieved_chunk_raises_even_from_another_document(bad_chunk):
    # Found in review: the first version only parsed a retrieved Chunk when
    # it shared a Document with a gold, so this case silently scored False
    # -- a miss -- instead of surfacing the bad data. Every retrieved Chunk
    # is now checked, whatever Document it's from.
    gold = [{"document_id": CP54, "locator": "1.1"}]
    with pytest.raises(ValueError):
        case_hit(gold, [bad_chunk])


def test_no_gold_locators_is_never_a_hit():
    # Unanswerable cases have none. The harness excludes them from recall
    # (ADR-0029), but case_hit itself must still give a sensible answer.
    assert not case_hit([], [_retrieved(CP54, "1.1", "clause_numbered")])


def test_nothing_retrieved_is_a_miss():
    assert not case_hit([{"document_id": CP54, "locator": "1.1"}], [])
