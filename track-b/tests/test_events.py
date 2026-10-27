# The Event writer (issue #44, ADR-0031): schema validation before insert,
# and stored Events carrying Redacted query and answer end to end. Needs the
# Postgres container (regdocs_test); chat model and retriever are fakes.

from pathlib import Path

import jsonschema
import psycopg
import pytest
from langchain_core.language_models.fake_chat_models import FakeListChatModel
from regdocs_schema.testing import load_json
from regdocs_store.testing import (
    DB_URL,
    clean_db,  # noqa: F401
    requires_postgres,
)
from regdocs_track_b.events import write_event
from regdocs_track_b.graph import answer_question, build_graph
from regdocs_track_b.testing import CHUNKS, FakeRetriever, safe_classifier, safe_judge

pytestmark = requires_postgres

FIXTURES = Path(__file__).parents[2] / "schema" / "fixtures"


def _stored_rows():
    with psycopg.connect(DB_URL) as conn:
        return conn.execute(
            "SELECT id, event_type, recorded_at, payload FROM events"
        ).fetchall()


def test_a_valid_event_is_stored_as_its_full_payload(clean_db):  # noqa: F811
    event = load_json(FIXTURES / "event" / "valid-full-run.json")

    write_event(event, DB_URL)

    [(event_id, event_type, recorded_at, payload)] = _stored_rows()
    assert event_id == event["id"]
    assert event_type == "QueryAnswered"
    assert recorded_at is not None
    assert payload == event


def test_each_event_type_is_validated_against_its_own_schema(clean_db):  # noqa: F811
    flagged = load_json(FIXTURES / "event-flagged" / "valid.json")
    overridden = load_json(FIXTURES / "answer-overridden" / "valid.json")

    write_event(flagged, DB_URL)
    write_event(overridden, DB_URL)

    stored_types = []
    for row in _stored_rows():
        stored_types.append(row[1])
    stored_types.sort()
    assert stored_types == ["AnswerOverridden", "EventFlagged"]


def test_an_event_failing_schema_validation_is_rejected_and_not_stored(
    clean_db,  # noqa: F811
):
    invalid = load_json(FIXTURES / "event" / "invalid-scrambled-step-order.json")

    with pytest.raises(jsonschema.ValidationError):
        write_event(invalid, DB_URL)

    assert _stored_rows() == []


def test_an_unknown_event_type_is_rejected(clean_db):  # noqa: F811
    with pytest.raises(ValueError, match="event_type"):
        write_event({"id": "x", "event_type": "Mystery"}, DB_URL)

    assert _stored_rows() == []


def test_a_pipeline_event_is_stored_with_redacted_query_and_answer(
    clean_db,  # noqa: F811
):
    graph = build_graph(
        retriever=FakeRetriever(documents=CHUNKS),
        chat_model=FakeListChatModel(responses=["We will reply to jane@x.ie."]),
        draft_model_name="fake-chat",
        classifier_model=safe_classifier(),
        classifier_model_name="fake-classifier",
        judge_model=safe_judge(),
        judge_model_name="fake-judge",
    )
    event = answer_question(graph, "My email is jane@x.ie, how much notice?")

    write_event(event, DB_URL)

    [(_, _, _, payload)] = _stored_rows()
    assert payload["query"] == "My email is [REDACTED:EMAIL], how much notice?"
    assert payload["answer"] == "We will reply to [REDACTED:EMAIL]."
    assert "jane@x.ie" not in str(payload)
