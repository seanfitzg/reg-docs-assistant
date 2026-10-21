# Track B's pipeline skeleton (issue #41): a LangGraph state graph with the
# four fixed Steps (classify, retrieve, draft, verify) that assembles an Event
# valid against /schema's event.schema.json from the first run.
#
# classify and verify are honest stubs, recorded under the model name "stub"
# (verify's confidence is 0.0, so nothing downstream mistakes it for a real
# groundedness score). retrieve uses the real retriever (ADR-0032); draft is a
# placeholder. Halting flags (ADR-0008, ADR-0009) and the real classify/verify
# are later work, so every run here takes all four Steps and raises no Flags.

import operator
import time
import uuid
from collections.abc import Callable
from typing import Annotated, TypedDict

from langchain_core.documents import Document
from langchain_core.language_models import BaseChatModel
from langchain_core.retrievers import BaseRetriever
from langgraph.graph import END, START, StateGraph

# retriever.py puts /store on sys.path and re-exports its embedding model.
from retriever import EMBEDDING_MODEL  # the retrieve Step's model

STUB_MODEL = "stub"

# Local-model Steps cost nothing; the first paid model arrives with the real
# draft.
LOCAL_COST = 0


class PipelineState(TypedDict):
    question: str
    chunks: list[Document]
    answer: str
    steps: Annotated[list[dict], operator.add]


def _step(
    clock: Callable[[], float], started: float, step_type: str, model: str, **extra
) -> dict:
    latency_ms = (clock() - started) * 1000
    return {
        "step_type": step_type,
        "model": model,
        "cost": LOCAL_COST,
        "latency_ms": latency_ms,
        **extra,
    }


def _pin_chunk(document: Document) -> dict:
    # Text is pinned, not just the id, so Replay can re-run against exactly
    # what was retrieved (ADR-0005).
    return {
        "chunk_id": document.metadata["chunk_id"],
        "document_id": document.metadata["document_id"],
        "text": document.page_content,
        "score": document.metadata["score"],
    }


def _draft_prompt(question: str, chunks: list[Document]) -> str:
    context_lines = []
    for chunk in chunks:
        context_lines.append(chunk.page_content)
    context = "\n\n".join(context_lines)
    return f"Answer the question using only this context.\n\n{context}\n\nQuestion: {question}"


def build_graph(
    retriever: BaseRetriever,
    chat_model: BaseChatModel,
    draft_model_name: str,
    # Monotonic, so a wall-clock adjustment mid-run can't give a negative
    # latency.
    clock: Callable[[], float] = time.perf_counter,
):
    def classify(state: PipelineState) -> dict:
        started = clock()
        return {"steps": [_step(clock, started, "classify", STUB_MODEL)]}

    def retrieve(state: PipelineState) -> dict:
        started = clock()
        chunks = retriever.invoke(state["question"])
        pinned = []
        for chunk in chunks:
            pinned.append(_pin_chunk(chunk))
        step = _step(
            clock, started, "retrieve", EMBEDDING_MODEL, retrieved_chunks=pinned
        )
        return {"chunks": chunks, "steps": [step]}

    def draft(state: PipelineState) -> dict:
        started = clock()
        response = chat_model.invoke(_draft_prompt(state["question"], state["chunks"]))
        step = _step(clock, started, "draft", draft_model_name)
        answer = response.content
        # The Event schema needs a non-empty string; some chat models return
        # a list of content blocks, which would otherwise surface later as an
        # invalid Event.
        if not isinstance(answer, str) or not answer.strip():
            raise ValueError(f"draft produced no usable answer text: {answer!r}")
        return {"answer": answer, "steps": [step]}

    def verify(state: PipelineState) -> dict:
        started = clock()
        return {"steps": [_step(clock, started, "verify", STUB_MODEL, confidence=0.0)]}

    graph = StateGraph(PipelineState)
    graph.add_node("classify", classify)
    graph.add_node("retrieve", retrieve)
    graph.add_node("draft", draft)
    graph.add_node("verify", verify)
    graph.add_edge(START, "classify")
    graph.add_edge("classify", "retrieve")
    graph.add_edge("retrieve", "draft")
    graph.add_edge("draft", "verify")
    graph.add_edge("verify", END)
    return graph.compile()


def answer_question(graph, question: str) -> dict:
    """Run `question` through the graph and assemble the finished run's Event."""
    final = graph.invoke({"question": question, "steps": []})
    return {
        "id": str(uuid.uuid4()),
        "event_type": "QueryAnswered",
        "query": question,
        "answer": final["answer"],
        "flags": [],
        "steps": final["steps"],
    }
