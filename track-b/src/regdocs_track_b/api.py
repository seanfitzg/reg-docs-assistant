# Track B's HTTP API (issue #45): POST /query runs the graph and stores the
# Event; GET /events/{id} reads a stored Event back. Synchronous, no streaming,
# no authentication.
#
# create_app takes the compiled graph and the database URL, so tests can inject
# a fake retriever and chat model; create_default_app wires the real local
# ones for `uvicorn --factory`.

import os

from fastapi import FastAPI, HTTPException
from ollama import ResponseError
from pydantic import BaseModel, Field
from regdocs_store.db import DEFAULT_DB_URL
from regdocs_store.embed import OllamaEmbeddingClient

from regdocs_track_b.events import read_event, write_event
from regdocs_track_b.graph import build_graph, run_question
from regdocs_track_b.retriever import ChunkRetriever

DRAFT_MODEL = "qwen2.5:7b-instruct"
CLASSIFIER_MODEL = "qwen2.5:7b-instruct"
# Overridable so a different model can judge the drafter (ADR-0035).
DEFAULT_JUDGE_MODEL = "qwen2.5:7b-instruct"


class QueryRequest(BaseModel):
    # The Event schema requires a non-empty query.
    question: str = Field(min_length=1)


class CitationResponse(BaseModel):
    marker: int
    chunk_id: str
    document_id: str
    locator: str


class QueryResponse(BaseModel):
    event_id: str
    # The stored answer, so a Redacted echo of the user's own PII stays
    # Redacted here too.
    answer: str
    citations: list[CitationResponse]
    flags: list[str]


def create_app(graph, db_url: str) -> FastAPI:
    app = FastAPI(title="RegDocs Assistant (Track B)")

    # Plain `def`, not `async def`: the graph blocks.
    @app.post("/query")
    def query(request: QueryRequest) -> QueryResponse:
        try:
            event, citations = run_question(graph, request.question)
        except ResponseError as error:
            # The model server failed (e.g. a looping model aborted by Ollama).
            raise HTTPException(status_code=502, detail=f"model error: {error}")
        write_event(event, db_url)
        return QueryResponse(
            event_id=event["id"],
            answer=event["answer"],
            citations=citations,
            flags=event["flags"],
        )

    @app.get("/events/{event_id}")
    def get_event(event_id: str) -> dict:
        event = read_event(event_id, db_url)
        if event is None:
            raise HTTPException(status_code=404, detail="event not found")
        return event

    return app


def create_default_app() -> FastAPI:
    # Imported here so importing api.py (the tests do) doesn't need
    # langchain-ollama's model client until the real app is built.
    from langchain_ollama import ChatOllama

    db_url = os.environ.get("STORE_DATABASE_URL", DEFAULT_DB_URL)
    judge_model = os.environ.get("JUDGE_MODEL") or DEFAULT_JUDGE_MODEL
    graph = build_graph(
        retriever=ChunkRetriever(
            db_url=db_url, embedding_client=OllamaEmbeddingClient()
        ),
        chat_model=ChatOllama(model=DRAFT_MODEL, temperature=0),
        draft_model_name=DRAFT_MODEL,
        classifier_model=ChatOllama(model=CLASSIFIER_MODEL, temperature=0),
        classifier_model_name=CLASSIFIER_MODEL,
        judge_model=ChatOllama(model=judge_model, temperature=0),
        judge_model_name=judge_model,
    )
    return create_app(graph, db_url)
