# Tests for event.schema.json, event-flagged.schema.json, and
# answer-overridden.schema.json (issue #4), plus relational checks that
# per-file validation can't express on its own: that EventFlagged/
# AnswerOverridden fixtures genuinely reference a real Event fixture by id,
# and that the halt-vs-annotate Flag behaviour (ADR-0006, 0008, 0009) holds
# on the actual fixture content, not just "the schema allows this shape".
#
# See test_harness.py and test_document_chunk.py for the basics (imports,
# pathlib, load_json/validate from support.py, dict indexing, pytest.raises,
# plain assert). This file only comments on constructs that are new here.

from pathlib import Path

import jsonschema
import pytest

from support import load_json, validate

SCHEMA_DIR = Path(__file__).parent.parent
EVENT_SCHEMA = SCHEMA_DIR / "event.schema.json"
EVENT_FLAGGED_SCHEMA = SCHEMA_DIR / "event-flagged.schema.json"
ANSWER_OVERRIDDEN_SCHEMA = SCHEMA_DIR / "answer-overridden.schema.json"
EVENT_FIXTURES = SCHEMA_DIR / "fixtures" / "event"
EVENT_FLAGGED_FIXTURES = SCHEMA_DIR / "fixtures" / "event-flagged"
ANSWER_OVERRIDDEN_FIXTURES = SCHEMA_DIR / "fixtures" / "answer-overridden"


# ---- Event schema: full run ----

def test_full_run_event_passes_validation():
    schema = load_json(EVENT_SCHEMA)
    payload = load_json(EVENT_FIXTURES / "valid-full-run.json")

    validate(payload, schema)


def test_full_run_event_has_all_four_steps_in_order():
    event = load_json(EVENT_FIXTURES / "valid-full-run.json")

    # [expr for item in iterable] is a *list comprehension* — Python's
    # built-in way of writing what C# LINQ does with
    # steps.Select(s => s["step_type"]).ToList(). It builds a new list by
    # evaluating step["step_type"] once per item in event["steps"], in
    # order, with no separate loop statement needed.
    step_types = [step["step_type"] for step in event["steps"]]

    # Comparing two Python lists with == checks every element in order —
    # value/structural equality, like C#'s Enumerable.SequenceEqual, not
    # reference equality. No special method call needed, unlike
    # list1.SequenceEqual(list2) in C#.
    assert step_types == ["classify", "retrieve", "draft", "verify"]


def test_retrieve_step_stores_pinned_chunk_text_not_just_id():
    event = load_json(EVENT_FIXTURES / "valid-full-run.json")

    retrieve_step = event["steps"][1]
    chunk = retrieve_step["retrieved_chunks"][0]

    # "in" here checks dict membership (does this key exist), same idea as
    # C#'s dict.ContainsKey(...). This is the direct proof for the
    # acceptance criterion: retrieve stores the actual chunk text alongside
    # the id, not the id alone.
    assert "chunk_id" in chunk
    assert "text" in chunk
    assert chunk["text"].startswith("A regulated entity shall provide")


# ---- Event schema: annotate-only flag doesn't halt ----

def test_full_run_with_annotate_only_flag_passes_validation():
    schema = load_json(EVENT_SCHEMA)
    payload = load_json(EVENT_FIXTURES / "valid-full-run-with-annotate-only-flag.json")

    validate(payload, schema)


def test_annotate_only_flag_does_not_reduce_step_count():
    event = load_json(EVENT_FIXTURES / "valid-full-run-with-annotate-only-flag.json")

    # len(...) is Python's built-in for "how many items", equivalent to a
    # C# collection's .Count property but called as a function on the
    # collection rather than a member of it: len(event["steps"]) rather
    # than event["steps"].Count.
    assert "low_confidence" in event["flags"]
    assert len(event["steps"]) == 4


# ---- Event schema: halted pipelines ----

def test_halted_at_classify_event_passes_validation():
    schema = load_json(EVENT_SCHEMA)
    payload = load_json(EVENT_FIXTURES / "valid-halted-at-classify.json")

    validate(payload, schema)


def test_halted_at_classify_has_only_classify_step():
    event = load_json(EVENT_FIXTURES / "valid-halted-at-classify.json")

    assert "possible_prompt_injection" in event["flags"]
    assert [step["step_type"] for step in event["steps"]] == ["classify"]


def test_halted_at_retrieve_event_passes_validation():
    schema = load_json(EVENT_SCHEMA)
    payload = load_json(EVENT_FIXTURES / "valid-halted-at-retrieve.json")

    validate(payload, schema)


def test_halted_at_retrieve_has_only_classify_and_retrieve_steps():
    event = load_json(EVENT_FIXTURES / "valid-halted-at-retrieve.json")

    assert "no_chunks_retrieved" in event["flags"]
    assert [step["step_type"] for step in event["steps"]] == ["classify", "retrieve"]


def test_no_chunks_retrieved_requires_the_retrieve_step_too():
    # no_chunks_retrieved means "retrieve ran and found nothing" — it does
    # NOT mean "retrieve never ran". This fixture has only classify, which
    # should fail: the flag requires exactly classify+retrieve, not just an
    # upper bound of at most 2 steps.
    schema = load_json(EVENT_SCHEMA)
    payload = load_json(EVENT_FIXTURES / "invalid-no-chunks-retrieved-missing-retrieve-step.json")

    with pytest.raises(jsonschema.exceptions.ValidationError):
        validate(payload, schema)


# ---- Event schema: invalid fixtures ----

def test_event_missing_steps_without_halting_flag_fails_validation():
    # This is the schema-level enforcement of the halt-vs-full-run rule:
    # three Steps (missing verify) with an empty flags array — no halting
    # Flag present to excuse the missing Steps.
    schema = load_json(EVENT_SCHEMA)
    payload = load_json(EVENT_FIXTURES / "invalid-missing-steps-no-halt-flag.json")

    with pytest.raises(jsonschema.exceptions.ValidationError):
        validate(payload, schema)


def test_invalid_event_fails_validation():
    schema = load_json(EVENT_SCHEMA)
    payload = load_json(EVENT_FIXTURES / "invalid-missing-required.json")

    with pytest.raises(jsonschema.exceptions.ValidationError):
        validate(payload, schema)


def test_event_cannot_carry_human_flagged_itself():
    # human_flagged can only ever be added after the fact, via a separate
    # EventFlagged record (ADR-0001) — an Event is never created with it
    # already in its own flags array. This fixture is otherwise a normal
    # complete 4-step run; human_flagged is the only thing wrong with it.
    schema = load_json(EVENT_SCHEMA)
    payload = load_json(EVENT_FIXTURES / "invalid-human-flagged-on-event.json")

    with pytest.raises(jsonschema.exceptions.ValidationError):
        validate(payload, schema)


def test_event_with_scrambled_step_order_fails_validation():
    # Same 4 Steps as a valid full run, just reordered (classify, verify,
    # draft, retrieve instead of classify, retrieve, draft, verify) — proves
    # the fixed order is positionally enforced, not just documented.
    schema = load_json(EVENT_SCHEMA)
    payload = load_json(EVENT_FIXTURES / "invalid-scrambled-step-order.json")

    with pytest.raises(jsonschema.exceptions.ValidationError):
        validate(payload, schema)


# ---- EventFlagged schema ----

def test_event_flagged_passes_validation():
    schema = load_json(EVENT_FLAGGED_SCHEMA)
    payload = load_json(EVENT_FLAGGED_FIXTURES / "valid.json")

    validate(payload, schema)


def test_event_flagged_references_an_existing_event_by_id():
    flagged = load_json(EVENT_FLAGGED_FIXTURES / "valid.json")
    referenced_event = load_json(EVENT_FIXTURES / "valid-full-run-with-annotate-only-flag.json")

    assert flagged["original_event_id"] == referenced_event["id"]


def test_invalid_event_flagged_fails_validation():
    schema = load_json(EVENT_FLAGGED_SCHEMA)
    payload = load_json(EVENT_FLAGGED_FIXTURES / "invalid-missing-required.json")

    with pytest.raises(jsonschema.exceptions.ValidationError):
        validate(payload, schema)


# ---- AnswerOverridden schema ----

def test_answer_overridden_passes_validation():
    schema = load_json(ANSWER_OVERRIDDEN_SCHEMA)
    payload = load_json(ANSWER_OVERRIDDEN_FIXTURES / "valid.json")

    validate(payload, schema)


def test_answer_overridden_references_an_existing_event_by_id():
    override = load_json(ANSWER_OVERRIDDEN_FIXTURES / "valid.json")
    referenced_event = load_json(EVENT_FIXTURES / "valid-full-run.json")

    assert override["original_event_id"] == referenced_event["id"]


def test_invalid_answer_overridden_fails_validation():
    schema = load_json(ANSWER_OVERRIDDEN_SCHEMA)
    payload = load_json(ANSWER_OVERRIDDEN_FIXTURES / "invalid-missing-required.json")

    with pytest.raises(jsonschema.exceptions.ValidationError):
        validate(payload, schema)
