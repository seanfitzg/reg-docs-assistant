# No requires_postgres: these tests point at a closed port on purpose.

from fastapi.testclient import TestClient
from langchain_core.language_models.fake_chat_models import FakeListChatModel
from regdocs_track_b.api import create_app
from regdocs_track_b.graph import build_graph
from regdocs_track_b.testing import CHUNKS, FakeRetriever, safe_classifier, safe_judge

UNREACHABLE_DB_URL = "postgresql://u:p@127.0.0.1:1/none?connect_timeout=2"


def _client():
    graph = build_graph(
        retriever=FakeRetriever(documents=CHUNKS),
        chat_model=FakeListChatModel(responses=["Thirty days' notice. [1]"]),
        draft_model_name="fake-chat",
        classifier_model=safe_classifier(),
        classifier_model_name="fake-classifier",
        judge_model=safe_judge(),
        judge_model_name="fake-judge",
    )
    return TestClient(create_app(graph, UNREACHABLE_DB_URL))


def test_a_query_with_the_database_down_returns_503():
    response = _client().post("/query", json={"question": "How much notice?"})

    assert response.status_code == 503
    assert "database unavailable" in response.json()["detail"]


def test_history_with_the_database_down_returns_503():
    response = _client().get("/queries")

    assert response.status_code == 503
