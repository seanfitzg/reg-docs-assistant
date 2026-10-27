# LLM_PROVIDER switches the real app between Ollama and OpenAI (ADR-0036).
# No fakes: each test builds the app uvicorn builds (create_default_app) and,
# past startup, sends a real POST /query through every Step.
#
# The two startup tests run by default. The rest are opt-in because they need
# the network or running services:
#   RUN_REAL_OPENAI=1   bad-key test (network only, free) and the OpenAI
#                       happy path (also needs OPENAI_API_KEY; spends a
#                       fraction of a cent)
#   RUN_REAL_PIPELINE=1 Ollama happy path (needs Postgres loaded and embedded,
#                       plus Ollama with both models pulled)
# The happy paths store a real Event in STORE_DATABASE_URL (default: regdocs).

import os

import pytest
from fastapi.testclient import TestClient
from regdocs_track_b.api import create_default_app
from regdocs_track_b.models import DEFAULT_MODELS

QUESTION = "What must a firm disclose?"

needs_openai = pytest.mark.skipif(
    not os.environ.get("RUN_REAL_OPENAI"),
    reason="opt-in: set RUN_REAL_OPENAI=1 (needs the network)",
)
needs_openai_key = pytest.mark.skipif(
    not os.environ.get("OPENAI_API_KEY"),
    reason="needs OPENAI_API_KEY",
)
needs_ollama_pipeline = pytest.mark.skipif(
    not os.environ.get("RUN_REAL_PIPELINE"),
    reason="opt-in: set RUN_REAL_PIPELINE=1 (needs Postgres + Ollama)",
)


def test_an_unknown_provider_stops_the_app_starting(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "carrier-pigeon")

    with pytest.raises(ValueError, match="carrier-pigeon"):
        create_default_app()


def test_settings_are_read_from_a_dotenv_file_in_the_working_directory(
    monkeypatch, tmp_path
):
    (tmp_path / ".env").write_text("LLM_PROVIDER=from-the-dotenv-file\n")
    monkeypatch.chdir(tmp_path)
    # monkeypatch restores this afterwards, undoing what the loader sets.
    monkeypatch.delenv("LLM_PROVIDER", raising=False)

    with pytest.raises(ValueError, match="from-the-dotenv-file"):
        create_default_app()


def test_a_real_environment_variable_beats_the_dotenv_file(monkeypatch, tmp_path):
    (tmp_path / ".env").write_text("LLM_PROVIDER=from-the-dotenv-file\n")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("LLM_PROVIDER", "from-the-environment")

    with pytest.raises(ValueError, match="from-the-environment"):
        create_default_app()


def test_the_openai_provider_refuses_to_start_without_a_key(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    with pytest.raises(ValueError, match="OPENAI_API_KEY"):
        create_default_app()


def test_an_openai_model_with_no_price_stops_the_app_starting(monkeypatch):
    # Unpriced, its Steps would record a cost of 0. A JUDGE_MODEL left over
    # from an Ollama run is the likely way to hit this.
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-not-a-real-key")
    monkeypatch.setenv("JUDGE_MODEL", "qwen2.5:7b-instruct")

    with pytest.raises(ValueError, match="qwen2.5:7b-instruct"):
        create_default_app()


@needs_openai
def test_openai_rejecting_the_key_is_a_502_not_a_500(monkeypatch):
    # A real call to OpenAI with a key it will refuse: free, and it fails at
    # classify, the first Step, so neither Postgres nor Ollama is reached.
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-not-a-real-key")
    client = TestClient(create_default_app(), raise_server_exceptions=False)

    response = client.post("/query", json={"question": QUESTION})

    assert response.status_code == 502
    assert "model error" in response.json()["detail"]


def _steps_by_type(client, event_id):
    event = client.get(f"/events/{event_id}").json()
    return {step["step_type"]: step for step in event["steps"]}


@needs_ollama_pipeline
def test_ollama_answers_end_to_end_and_costs_nothing(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "ollama")
    client = TestClient(create_default_app())

    response = client.post("/query", json={"question": QUESTION})

    assert response.status_code == 200
    steps = _steps_by_type(client, response.json()["event_id"])
    assert steps["draft"]["model"] == DEFAULT_MODELS["ollama"]
    assert steps["draft"]["cost"] == 0


@needs_openai
@needs_openai_key
@needs_ollama_pipeline
def test_openai_answers_end_to_end_and_the_paid_steps_record_a_cost(monkeypatch):
    # Retrieval still embeds locally, so this needs Ollama's nomic-embed-text
    # and the loaded store as well as the key.
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    client = TestClient(create_default_app())

    response = client.post("/query", json={"question": QUESTION})

    assert response.status_code == 200
    steps = _steps_by_type(client, response.json()["event_id"])
    assert steps["draft"]["model"] == DEFAULT_MODELS["openai"]
    assert steps["draft"]["cost"] > 0
    assert steps["verify"]["cost"] > 0
    assert steps["retrieve"]["cost"] == 0
