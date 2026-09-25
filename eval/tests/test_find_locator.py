# Unit tests for find_locator.search (issue #29): the keyword-search helper
# used while hand-writing Eval Cases, to copy exact (document_id, locator)
# pairs rather than typing them from memory.

from pathlib import Path

import pytest

from corpus import load_active_chunks
from find_locator import main, search

FIXTURE_OUTPUT = Path(__file__).parent / "fixtures" / "ingestion-output"


def _chunks():
    return load_active_chunks(FIXTURE_OUTPUT)


def test_match_is_case_insensitive_and_returns_document_and_locator():
    matches = search(_chunks(), "KEY INFORMATION")

    # A list comprehension -- the list equivalent of the set comprehension
    # in test_check_dataset.py, like matches.Select(m => ...).ToList().
    assert [(m.document_id, m.locator) for m in matches] == [("doc-a", "3.12")]


def test_every_term_must_appear_but_not_necessarily_adjacent():
    # Terms are ANDed, not matched as one phrase: in the chunk text,
    # "comprehensive" and "consumer" are split by a line break from PDF
    # extraction, which an exact-phrase match would miss.
    matches = search(_chunks(), "comprehensive consumer framework")

    assert [(m.document_id, m.locator) for m in matches] == [("doc-a", "1.1")]


def test_inactive_generation_chunks_are_never_returned():
    # This word only appears in doc-a's inactive gen-1 "9.9" Chunk (which
    # also mentions "key information document" -- the first test above
    # only finds 3.12, so it proves the same thing from the other side).
    matches = search(_chunks(), "inactive-generation")

    assert matches == []


def test_document_filter_restricts_results_to_one_document():
    # "regulated entity" appears in both doc-a 3.12 and doc-b's Introduction.
    assert len(search(_chunks(), "regulated entity")) == 2

    matches = search(_chunks(), "regulated entity", document_id="doc-b")

    assert [(m.document_id, m.locator) for m in matches] == [("doc-b", "Introduction (p. 3)")]


def test_snippet_shows_the_match_with_whitespace_collapsed():
    # Destructuring: [match] = ... unpacks a one-item list into one
    # variable, and raises ValueError if the list has any other length --
    # so this line also asserts "exactly one result".
    [match] = search(_chunks(), "comprehensive")

    # PDF line breaks and double spaces flattened to single spaces, so the
    # snippet prints on one terminal line.
    assert "comprehensive consumer protection" in match.snippet
    assert "\n" not in match.snippet


def test_no_match_returns_empty_list():
    assert search(_chunks(), "cryptocurrency") == []


@pytest.mark.parametrize("blank", ["", "   "])
def test_blank_terms_are_rejected(blank):
    # Caught by /code-review: "".split() is [], and all() over an empty
    # sequence is True (nothing failed the test -- "vacuous truth"), so
    # every Chunk "matched" and then indexing the first term crashed.
    # pytest.raises(..., match=...) also checks the message, by regex.
    with pytest.raises(ValueError, match="at least one search term"):
        search(_chunks(), blank)


# ---- main (the command-line entry point) ----

def test_cli_rejects_blank_terms_with_a_usage_error():
    # parser.error() exits via SystemExit rather than returning -- Python's
    # sys.exit() is an exception, so pytest.raises can catch it. Exit code
    # 2 is argparse's convention for a usage error.
    with pytest.raises(SystemExit) as exit_info:
        main(["   ", "--output-dir", str(FIXTURE_OUTPUT)])

    assert exit_info.value.code == 2


def test_cli_reports_an_unknown_document_id(capsys):
    # capsys is a built-in pytest fixture: naming it as a parameter makes
    # pytest inject it, and it captures what the code under test printed.
    exit_code = main(["consumer", "--doc", "doc-typo", "--output-dir", str(FIXTURE_OUTPUT)])

    assert exit_code == 1
    assert "No Document with id 'doc-typo'" in capsys.readouterr().err
