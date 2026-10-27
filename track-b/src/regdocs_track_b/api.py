# Track B's HTTP API (issue #45): POST /query runs the graph and stores the
# Event; GET /events/{id} reads a stored Event back. Synchronous, no streaming,
# no authentication.
#
# create_app takes the compiled graph and the database URL, so tests can inject
# a fake retriever and chat model; create_default_app wires the real local
# ones for `uvicorn --factory`.

import os

import psycopg
from dotenv import find_dotenv, load_dotenv
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from psycopg.conninfo import make_conninfo
from pydantic import BaseModel, Field
from regdocs_store.db import DEFAULT_DB_URL
from regdocs_store.embed import OllamaEmbeddingClient

from regdocs_track_b.events import list_queries, read_event, write_event
from regdocs_track_b.graph import build_graph, run_question
from regdocs_track_b.models import (
    DEFAULT_MODELS,
    PROVIDER_ERRORS,
    build_chat_model,
    provider_from_env,
)
from regdocs_track_b.retriever import ChunkRetriever

HISTORY_PAGE_SIZE = 20
DB_CONNECT_TIMEOUT_SECONDS = 5


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


class QueryHistoryItem(BaseModel):
    event_id: str
    recorded_at: str
    query: str


class QueryHistoryResponse(BaseModel):
    items: list[QueryHistoryItem]
    total: int
    page: int
    page_size: int


def create_app(graph, db_url: str) -> FastAPI:
    app = FastAPI(title="RegDocs Assistant (Track B)")

    @app.exception_handler(psycopg.OperationalError)
    def database_unavailable(request: Request, error: psycopg.OperationalError):
        return JSONResponse(
            status_code=503,
            content={"detail": "database unavailable: is Postgres (docker) running?"},
        )

    # Plain `def`, not `async def`: the graph blocks.
    @app.post("/query")
    def query(request: QueryRequest) -> QueryResponse:
        try:
            event, citations = run_question(graph, request.question)
        except PROVIDER_ERRORS as error:
            # The model server failed (e.g. a looping model aborted by Ollama,
            # or OpenAI out of credit).
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

    @app.get("/queries")
    def get_queries(page: int = Query(1, ge=1)) -> QueryHistoryResponse:
        items, total = list_queries(
            db_url, limit=HISTORY_PAGE_SIZE, offset=(page - 1) * HISTORY_PAGE_SIZE
        )
        return QueryHistoryResponse(
            items=items, total=total, page=page, page_size=HISTORY_PAGE_SIZE
        )

    return app


def create_default_app() -> FastAPI:
    # Searches up from the working directory (the repo root under uvicorn).
    # Never overrides a variable already set in the environment.
    load_dotenv(find_dotenv(usecwd=True))
    # Without a timeout, a database that accepts the connection but never
    # answers (Docker stopped) leaves the request hanging.
    db_url = make_conninfo(
        os.environ.get("STORE_DATABASE_URL", DEFAULT_DB_URL),
        connect_timeout=DB_CONNECT_TIMEOUT_SECONDS,
    )
    provider = provider_from_env()
    model_name = DEFAULT_MODELS[provider]
    judge_model = os.environ.get("JUDGE_MODEL") or model_name
    graph = build_graph(
        retriever=ChunkRetriever(
            db_url=db_url, embedding_client=OllamaEmbeddingClient()
        ),
        chat_model=build_chat_model(provider, model_name),
        draft_model_name=model_name,
        classifier_model=build_chat_model(provider, model_name),
        classifier_model_name=model_name,
        judge_model=build_chat_model(provider, judge_model),
        judge_model_name=judge_model,
    )
    return create_app(graph, db_url)
