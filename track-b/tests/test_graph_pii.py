# Graph-seam tests for PII detection and Redaction (issue #43, ADR-0008): a
# query with PII raises pii_detected but the pipeline still answers, and the
# finished Event stores placeholders. The retriever and chat model are fakes,
# so it runs offline.

from pathlib import Path

import pytest
from langchain_core.language_models.fake_chat_models import FakeListChatModel

from regdocs_schema.testing import load_json, validate
from regdocs_track_b.graph import answer_question, build_graph
from regdocs_track_b.testing import (
    CHUNKS,
    FakeRetriever,
    RecordingModel,
    make_chunk,
    safe_classifier,
    safe_judge,
)

EVENT_SCHEMA = load_json(
    Path(__file__).parent.parent.parent / "schema" / "event.schema.json"
)

EMAIL_QUERY = "My email is jane@x.ie, how much notice must a firm give?"


def _graph(answer="Thirty days.", chunks=CHUNKS, model=None):
    return build_graph(
        retriever=FakeRetriever(documents=chunks),
        chat_model=model or FakeListChatModel(responses=[answer]),
        draft_model_name="fake-chat",
        classifier_model=safe_classifier(),
        classifier_model_name="fake-classifier",
        judge_model=safe_judge(),
        judge_model_name="fake-judge",
    )


def _event(question, **kwargs):
    return answer_question(_graph(**kwargs), question)


def test_a_query_with_pii_raises_pii_detected_and_the_pipeline_still_answers():
    event = _event(EMAIL_QUERY)

    assert event["flags"] == ["pii_detected"]
    step_types = []
    for step in event["steps"]:
        step_types.append(step["step_type"])
    assert step_types == ["classify", "retrieve", "draft", "verify"]
    assert event["answer"] == "Thirty days."


def test_the_event_stores_typed_placeholders_instead_of_the_pii():
    event = _event(EMAIL_QUERY, answer="We will reply to jane@x.ie within 30 days.")

    assert event["query"] == (
        "My email is [REDACTED:EMAIL], how much notice must a firm give?"
    )
    assert event["answer"] == "We will reply to [REDACTED:EMAIL] within 30 days."
    validate(event, EVENT_SCHEMA)


def test_draft_still_sees_the_original_text():
    model = RecordingModel(responses=["Thirty days."], prompts=[])

    _event(EMAIL_QUERY, model=model)

    assert "jane@x.ie" in model.prompts[0]
    assert "[REDACTED" not in model.prompts[0]


def test_retrieved_chunk_text_is_not_redacted():
    chunks = [
        make_chunk(
            "c-1", "doc-a", "3.1", "Write to info@centralbank.ie for queries.", 0.9
        )
    ]

    event = _event(EMAIL_QUERY, chunks=chunks)

    retrieve = event["steps"][1]
    assert retrieve["retrieved_chunks"][0]["text"] == (
        "Write to info@centralbank.ie for queries."
    )


@pytest.mark.parametrize(
    "question",
    [
        EMAIL_QUERY,
        "Call me on 087 123 4567 and email jane@x.ie about notice",
        "How much notice must a firm give?",
    ],
)
def test_the_flag_and_the_redaction_come_from_the_same_detections(question):
    event = _event(question)

    flagged = "pii_detected" in event["flags"]
    redacted = "[REDACTED:" in event["query"]
    assert flagged == redacted


def test_a_query_without_pii_is_stored_unchanged_with_no_flags():
    event = _event("How much notice must a firm give?")

    assert event["flags"] == []
    assert event["query"] == "How much notice must a firm give?"
    validate(event, EVENT_SCHEMA)


def test_classify_is_recorded_as_rule_based_not_a_model():
    classify = _event(EMAIL_QUERY)["steps"][0]

    assert classify["model"] == "fake-classifier"
    assert classify["cost"] == 0
