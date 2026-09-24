# Unit tests for find_locator.search (issue #29): the keyword-search helper
# used while hand-writing Eval Cases, to copy exact (document_id, locator)
# pairs rather than typing them from memory.

from pathlib import Path

from corpus import load_active_chunks
from find_locator import search

FIXTURE_OUTPUT = Path(__file__).parent / "fixtures" / "ingestion-output"


def _chunks():
    return load_active_chunks(FIXTURE_OUTPUT)


def test_match_is_case_insensitive_and_returns_document_and_locator():
    hits = search(_chunks(), "KEY INFORMATION")

    # A list comprehension -- the list equivalent of the set comprehension
    # in test_check_dataset.py, like hits.Select(h => ...).ToList().
    assert [(h.document_id, h.locator) for h in hits] == [("doc-a", "3.12")]


def test_every_term_must_appear_but_not_necessarily_adjacent():
    # Terms are ANDed, not matched as one phrase: in the chunk text,
    # "comprehensive" and "consumer" are split by a line break from PDF
    # extraction, which an exact-phrase match would miss.
    hits = search(_chunks(), "comprehensive consumer framework")

    assert [(h.document_id, h.locator) for h in hits] == [("doc-a", "1.1")]


def test_inactive_generation_chunks_are_never_returned():
    # This word only appears in doc-a's inactive gen-1 "9.9" Chunk (which
    # also mentions "key information document" -- the first test above
    # only finds 3.12, so it proves the same thing from the other side).
    hits = search(_chunks(), "inactive-generation")

    assert hits == []


def test_document_filter_restricts_results_to_one_document():
    # "regulated entity" appears in both doc-a 3.12 and doc-b's Introduction.
    assert len(search(_chunks(), "regulated entity")) == 2

    hits = search(_chunks(), "regulated entity", document_id="doc-b")

    assert [(h.document_id, h.locator) for h in hits] == [("doc-b", "Introduction (p. 3)")]


def test_snippet_shows_the_match_with_whitespace_collapsed():
    [hit] = search(_chunks(), "comprehensive")

    # PDF line breaks and double spaces flattened to single spaces, so the
    # snippet prints on one terminal line.
    assert "comprehensive consumer protection" in hit.snippet
    assert "\n" not in hit.snippet


def test_no_match_returns_empty_list():
    assert search(_chunks(), "cryptocurrency") == []
