# Unit tests for the eval set's relational checks (issue #29): things
# eval-dataset.schema.json can't express because they need more than the
# file's own shape -- unique case ids, and Gold Locators that genuinely
# exist among the ingested Chunks.
#
# Runs against small fixture copies of ingestion/output (tests/fixtures/),
# not the real corpus, so it always runs -- test_dataset.py is the one that
# checks the real eval/dataset.json against the real ingestion output.

import copy
import json
from pathlib import Path

from check_dataset import find_problems
from corpus import load_active_chunks

FIXTURES = Path(__file__).parent / "fixtures"
FIXTURE_OUTPUT = FIXTURES / "ingestion-output"


# The leading underscore marks a helper as private to this module by
# convention only -- Python has no access modifiers, so nothing enforces it.
# pytest also ignores it as a test, since it doesn't start with "test_".
def _valid_dataset() -> dict:
    # A fresh copy per test, so one test mutating it can't leak into
    # another -- json.loads always builds new objects, so no shared state.
    return json.loads((FIXTURES / "valid-dataset.json").read_text(encoding="utf-8"))


# ---- load_active_chunks ----

def test_only_active_generation_chunks_are_loaded():
    chunks = load_active_chunks(FIXTURE_OUTPUT)

    # A set comprehension: {expression for item in iterable} builds a set
    # in one line -- like chunks.Select(c => (c.DocumentId, c.Locator))
    # .ToHashSet(), with each element a (document_id, locator) tuple.
    pairs = {(c["document_id"], c["locator"]) for c in chunks}

    # doc-a's "9.9" only exists in its inactive gen-1, so it must not be
    # here: retrieval never sees it, so a Gold Locator can't point at it.
    assert pairs == {("doc-a", "1.1"), ("doc-a", "3.12"), ("doc-b", "Introduction (p. 3)")}


# ---- find_problems ----

def test_valid_dataset_has_no_problems():
    assert find_problems(_valid_dataset(), load_active_chunks(FIXTURE_OUTPUT)) == []


def test_duplicate_case_id_is_reported():
    dataset = _valid_dataset()
    # copy.deepcopy clones the whole nested dict, so editing the copy's id
    # doesn't also change the original case (a plain assignment would just
    # be a second reference to the same object, as in C#).
    duplicate = copy.deepcopy(dataset["cases"][0])
    dataset["cases"].append(duplicate)

    problems = find_problems(dataset, load_active_chunks(FIXTURE_OUTPUT))

    assert problems == ["duplicate case id: q01"]


def test_missing_gold_locator_is_reported_with_case_id_and_locator():
    dataset = _valid_dataset()
    # "3.2" is a plausible typo for "3.12" -- exactly the silent error this
    # check exists to catch before it becomes a permanent retrieval miss.
    dataset["cases"][0]["gold_locators"][0]["locator"] = "3.2"

    problems = find_problems(dataset, load_active_chunks(FIXTURE_OUTPUT))

    assert problems == ["q01: gold locator not found in active Chunks: doc-a / 3.2"]


def test_gold_locator_only_in_inactive_generation_is_reported():
    dataset = _valid_dataset()
    dataset["cases"][0]["gold_locators"][0]["locator"] = "9.9"

    problems = find_problems(dataset, load_active_chunks(FIXTURE_OUTPUT))

    assert problems == ["q01: gold locator not found in active Chunks: doc-a / 9.9"]


def test_gold_locator_in_wrong_document_is_reported():
    dataset = _valid_dataset()
    # The locator string exists, but under a different Document -- the
    # check is on the (document_id, locator) pair, not the locator alone.
    dataset["cases"][0]["gold_locators"][0]["document_id"] = "doc-b"

    problems = find_problems(dataset, load_active_chunks(FIXTURE_OUTPUT))

    assert problems == ["q01: gold locator not found in active Chunks: doc-b / 3.12"]


def test_missing_superseded_locator_is_reported():
    dataset = _valid_dataset()
    dataset["cases"][1]["superseded_locators"][0]["locator"] = "Introduction (p. 4)"

    problems = find_problems(dataset, load_active_chunks(FIXTURE_OUTPUT))

    assert problems == [
        "q02: superseded locator not found in active Chunks: doc-b / Introduction (p. 4)"
    ]
