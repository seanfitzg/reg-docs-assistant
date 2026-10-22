# The HTTP API seam (issue #45), against regdocs_test with a fake retriever
# and scripted fake chat model: only Postgres needs to be running.

from pathlib import Path

import psycopg
from fastapi.testclient import TestClient
from langchain_core.language_models.fake_chat_models import FakeListChatModel
from regdocs_schema.testing import load_json, validate
from regdocs_store.testing import (
    DB_URL,
    clean_db,  # noqa: F401
    requires_postgres,
)
from regdocs_track_b.api import create_app
from regdocs_track_b.graph import build_graph
from regdocs_track_b.testing import CHUNKS, FakeRetriever

pytestmark = requires_postgres

EVENT_SCHEMA = load_json(
    Path(__file__).parent.parent.parent / "schema" / "event.schema.json"
)

QUESTION = "How much notice must a firm give?"


def _client(answer="Thirty days' notice. [1]"):
    graph = build_graph(
        retriever=FakeRetriever(documents=CHUNKS),
        chat_model=FakeListChatModel(responses=[answer]),
        draft_model_name="fake-chat",
    )
    return TestClient(create_app(graph, DB_URL))


def test_post_query_returns_event_id_answer_citations_and_flags(clean_db):  # noqa: F811
    response = _client().post("/query", json={"question": QUESTION})

    assert response.status_code == 200
    body = response.json()
    assert body["event_id"]
    assert body["answer"] == "Thirty days' notice. [1]"
    assert body["citations"] == [
        {"marker": 1, "chunk_id": "c-1", "document_id": "doc-a", "locator": "3.1"}
    ]
    assert body["flags"] == []


def test_the_event_a_query_names_is_stored_and_retrievable(clean_db):  # noqa: F811
    client = _client()
    posted = client.post("/query", json={"question": QUESTION}).json()

    response = client.get(f"/events/{posted['event_id']}")

    assert response.status_code == 200
    event = response.json()
    assert event["id"] == posted["event_id"]
    assert event["event_type"] == "QueryAnswered"
    assert event["query"] == QUESTION
    validate(event, EVENT_SCHEMA)


def test_an_unknown_event_id_returns_not_found(clean_db):  # noqa: F811
    response = _client().get("/events/does-not-exist")

    assert response.status_code == 404


def test_a_query_with_pii_is_flagged_and_stored_redacted(clean_db):  # noqa: F811
    client = _client()

    posted = client.post(
        "/query", json={"question": "My email is jane@x.ie, how much notice?"}
    ).json()
    stored = client.get(f"/events/{posted['event_id']}").json()

    assert posted["flags"] == ["pii_detected"]
    assert stored["query"] == "My email is [REDACTED:EMAIL], how much notice?"


def test_an_empty_question_is_rejected_and_nothing_is_stored(clean_db):  # noqa: F811
    client = _client()

    response = client.post("/query", json={"question": ""})

    assert response.status_code == 422
    with psycopg.connect(DB_URL) as conn:
        stored = conn.execute("SELECT count(*) FROM events").fetchone()[0]
    assert stored == 0
