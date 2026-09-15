# Tests for the clause_numbered chunking strategy (ADR-0014): splitting a
# cleaned document's text into Chunks at decimal clause numbers like "1.1",
# with the bare clause number as the locator (Q5 in the grilling session --
# no page number needed, since "1.1" is already directly searchable in the
# source PDF).
#
# The patterns exercised here (a heading line under the number, a number
# followed immediately by body text, a trailing period after the number)
# all come from inspecting the real target document (CP54) directly, not
# guesswork -- real regulatory-PDF text extraction is inconsistent about
# which of these shapes shows up where.

from pathlib import Path

import pytest

from strategies.clause_numbered import chunk, chunk_document

CORPUS_DIR = Path(__file__).parent.parent.parent / "corpus"
CP54_PDF = CORPUS_DIR / "04-cp54-second-consultation-consumer-protection-code.pdf"

requires_corpus = pytest.mark.skipif(
    not CP54_PDF.exists(),
    reason="corpus PDFs aren't committed to git -- see corpus/SOURCES.md to download them",
)


def test_splits_on_each_clause_number():
    text = "1.1\nPurpose\nThe purpose is X.\n1.2\nScope\nThe scope is Y."

    chunks = chunk(text)

    assert [c["locator"] for c in chunks] == ["1.1", "1.2"]


def test_chunk_text_is_everything_up_to_the_next_clause_number():
    text = "1.1\nPurpose\nThe purpose is X.\n1.2\nScope\nThe scope is Y."

    chunks = chunk(text)

    assert chunks[0]["text"] == "Purpose\nThe purpose is X."
    assert chunks[1]["text"] == "Scope\nThe scope is Y."


def test_trailing_period_after_the_clause_number_is_not_part_of_the_locator():
    # Real example from CP54: "1.9." (with a trailing period) immediately
    # followed by "Responses Sought" on the next line.
    text = "1.9.\nResponses Sought\nWhile we are providing an opportunity."

    chunks = chunk(text)

    assert chunks[0]["locator"] == "1.9"
    assert chunks[0]["text"] == "Responses Sought\nWhile we are providing an opportunity."


def test_clause_number_directly_followed_by_body_text_on_the_same_line():
    # Real example from CP54: "1.11  In relation to other matters..." --
    # no separate heading line, body starts right after the number.
    text = "1.11  In relation to other matters raised, we have reached a final position."

    chunks = chunk(text)

    assert chunks[0]["locator"] == "1.11"
    assert chunks[0]["text"] == "In relation to other matters raised, we have reached a final position."


def test_two_digit_second_component_is_not_mistaken_for_two_clauses():
    # A naive pattern could match "1.1" as a prefix of "1.10" and leave a
    # stray "0" behind. \d{1,3} is greedy, so it must consume all of "10".
    text = "1.1\nFirst.\n1.10\nTenth."

    chunks = chunk(text)

    assert [c["locator"] for c in chunks] == ["1.1", "1.10"]


def test_text_before_the_first_clause_number_is_discarded():
    # Front matter/preamble (cover page, table of contents) doesn't belong
    # to any clause and isn't a citable unit -- it's simply not chunked.
    text = "Second Consultation on Review of Consumer Protection Code\n1.1\nPurpose\nThe purpose is X."

    chunks = chunk(text)

    assert len(chunks) == 1
    assert chunks[0]["locator"] == "1.1"


def test_no_clause_numbers_produces_no_chunks():
    text = "This document has no numbered clauses anywhere in it."

    chunks = chunk(text)

    assert chunks == []


@requires_corpus
def test_chunk_document_extracts_cleans_and_chunks_the_real_pdf_end_to_end():
    # chunk() alone (tested above) never touches a PDF -- this proves the
    # extract -> clean -> chunk wiring chunk_document() adds on top of it
    # actually works together against the real corpus, not just in theory.
    chunks = chunk_document(CP54_PDF)

    assert any(c["locator"] == "1.8" for c in chunks)
    assert all("Consultation Paper CP 54" not in c["text"] for c in chunks)
