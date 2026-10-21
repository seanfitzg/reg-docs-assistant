# Single-seam test for graph.py (issue #41): answer_question(graph, question)
# -> Event. The retriever and chat model are fakes, so it runs offline.

import json
from pathlib import Path

import pytest

from langchain_core.documents import Document
from langchain_core.language_models.fake_chat_models import FakeListChatModel
from langchain_core.retrievers import BaseRetriever

from graph import answer_question, build_graph
from retriever import EMBEDDING_MODEL
from support import load_json, validate

EVENT_SCHEMA = load_json(
    Path(__file__).parent.parent.parent / "schema" / "event.schema.json"
)


class FakeRetriever(BaseRetriever):
    documents: list[Document]

    def _get_relevant_documents(self, query, *, run_manager):
        return self.documents


def _chunk(chunk_id, document_id, text, score):
    return Document(
        page_content=text,
        metadata={"chunk_id": chunk_id, "document_id": document_id, "score": score},
    )


CHUNKS = [
    _chunk("c-1", "doc-a", "Firms must give 30 days' notice.", 0.91),
    _chunk("c-2", "doc-b", "Fees must be disclosed.", 0.74),
]


class FakeClock:
    # Each reading is 0.25s after the last, so every node, which reads the
    # clock once before and once after its work, measures exactly 250 ms.
    def __init__(self):
        self._now = 0.0

    def __call__(self):
        self._now += 0.25
        return self._now


def _run(question="How much notice?", answer="Thirty days."):
    graph = build_graph(
        retriever=FakeRetriever(documents=CHUNKS),
        chat_model=FakeListChatModel(responses=[answer]),
        draft_model_name="fake-chat",
        clock=FakeClock(),
    )
    return answer_question(graph, question)


def test_event_validates_against_the_event_schema():
    event = _run()

    validate(event, EVENT_SCHEMA)
    json.dumps(event)
    assert event["query"] == "How much notice?"
    assert event["answer"] == "Thirty days."


def test_steps_run_in_order_with_zero_cost_and_measured_latency():
    event = _run()

    step_types = []
    for step in event["steps"]:
        step_types.append(step["step_type"])
        assert step["cost"] == 0
        assert step["latency_ms"] == 250
    assert step_types == ["classify", "retrieve", "draft", "verify"]


def test_stub_steps_are_recorded_under_the_model_name_stub():
    classify, retrieve, draft, verify = _run()["steps"]

    assert classify["model"] == "stub"
    assert verify["model"] == "stub"
    assert verify["confidence"] == 0.0
    assert retrieve["model"] == EMBEDDING_MODEL
    assert draft["model"] == "fake-chat"


def test_retrieve_step_pins_chunk_ids_text_and_scores():
    retrieve = _run()["steps"][1]

    assert retrieve["retrieved_chunks"] == [
        {
            "chunk_id": "c-1",
            "document_id": "doc-a",
            "text": "Firms must give 30 days' notice.",
            "score": 0.91,
        },
        {
            "chunk_id": "c-2",
            "document_id": "doc-b",
            "text": "Fees must be disclosed.",
            "score": 0.74,
        },
    ]


def test_a_blank_model_answer_fails_loudly_instead_of_yielding_an_invalid_event():
    with pytest.raises(ValueError, match="draft"):
        _run(answer="")
