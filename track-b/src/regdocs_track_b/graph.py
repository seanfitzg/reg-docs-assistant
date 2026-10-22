# Track B's pipeline skeleton (issue #41): a LangGraph state graph with the
# four fixed Steps (classify, retrieve, draft, verify) that assembles an Event
# valid against /schema's event.schema.json from the first run.
#
# verify is an honest stub, recorded under the model name "stub" (its
# confidence is 0.0, so nothing downstream mistakes it for a real groundedness
# score). classify runs the PII rules (issue #43, ADR-0008): a match raises
# pii_detected, which never halts the run, and answer_question redacts the
# finished Event from those same matches. Its injection half is still
# unbuilt. retrieve uses the real retriever (ADR-0032); draft prompts from a
# versioned file and resolves its [n] markers to Citations (issue #42,
# ADR-0010). The halting Flags (ADR-0008, ADR-0009) and the real verify are
# later work, so every run here takes all four Steps.

import operator
import re
import time
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Annotated, TypedDict

from langchain_core.documents import Document
from langchain_core.language_models import BaseChatModel
from langchain_core.retrievers import BaseRetriever
from langgraph.graph import END, START, StateGraph

from regdocs_store.embed import EMBEDDING_MODEL  # the retrieve Step's model
from regdocs_track_b.pii import PiiMatch, detect_pii, redact_answer, redact_query

STUB_MODEL = "stub"
# classify's PII half is deterministic rules, so no model is involved.
RULES_MODEL = "rules"

# The prompt is a versioned file, not a string in code: a new version is a new
# file beside the old ones, which stay readable for Replay (ADR-0005).
DEFAULT_DRAFT_PROMPT_PATH = Path(__file__).parents[2] / "prompts" / "draft-v1.txt"

# Local-model Steps cost nothing; the first paid model arrives with the real
# draft.
LOCAL_COST = 0


class PipelineState(TypedDict):
    question: str
    pii: list[PiiMatch]
    flags: Annotated[list[str], operator.add]
    chunks: list[Document]
    answer: str
    citations: list[dict]
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


def _draft_prompt(template: str, question: str, chunks: list[Document]) -> str:
    blocks = []
    for number, chunk in enumerate(chunks, start=1):
        blocks.append(f"[{number}] {chunk.page_content}")
    formattedTemplate = template.format(context="\n\n".join(blocks), question=question)
    return formattedTemplate


MARKER = re.compile(r"([ \t]*)\[(\d+)\]([ \t]*)")


def _resolve_citations(answer: str, chunks: list[Document]) -> tuple[str, list[dict]]:
    """Return the answer with unresolvable markers stripped, and its Citations.

    Marker n is the n-th retrieved Chunk (1-based, rank order). A number that
    maps to no Chunk is dropped rather than guessed at (ADR-0010).
    """
    citations = []
    cited = set()

    def keep_or_strip(match: re.Match) -> str:
        number = int(match.group(2))
        if not 1 <= number <= len(chunks):
            # Drop the marker and the spacing on one side, so "a [9]." and
            # "a [9] b" stay tidy and a paragraph-leading marker leaves no
            # stray space.
            before = answer[match.start() - 1 : match.start()]
            if before in ("", "\n"):
                return ""
            return match.group(3)
        if number not in cited:
            cited.add(number)
            chunk = chunks[number - 1]
            citations.append(
                {
                    "marker": number,
                    "chunk_id": chunk.metadata["chunk_id"],
                    "document_id": chunk.metadata["document_id"],
                    "locator": chunk.metadata["locator"],
                }
            )
        return match.group(0)

    cleaned = MARKER.sub(keep_or_strip, answer).strip()
    return cleaned, citations


def build_graph(
    retriever: BaseRetriever,
    chat_model: BaseChatModel,
    draft_model_name: str,
    draft_prompt_path: Path = DEFAULT_DRAFT_PROMPT_PATH,
    # Monotonic, so a wall-clock adjustment mid-run can't give a negative
    # latency.
    clock: Callable[[], float] = time.perf_counter,
):
    # Read now, not per question, so a missing prompt fails at startup.
    draft_template = draft_prompt_path.read_text(encoding="utf-8")

    def classify(state: PipelineState) -> dict:
        started = clock()
        matches = detect_pii(state["question"])
        flags = []
        if matches:
            flags.append("pii_detected")
        step = _step(clock, started, "classify", RULES_MODEL)
        return {"pii": matches, "flags": flags, "steps": [step]}

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
        response = chat_model.invoke(
            _draft_prompt(draft_template, state["question"], state["chunks"])
        )
        step = _step(clock, started, "draft", draft_model_name)
        raw_answer = response.content
        answer = ""
        citations = []
        # Some chat models return a list of content blocks, not a string.
        if isinstance(raw_answer, str):
            answer, citations = _resolve_citations(raw_answer, state["chunks"])
        # The Event schema needs a non-empty answer. Checked after stripping,
        # since an answer of only bad markers ends up blank.
        if not answer:
            raise ValueError(f"draft produced no usable answer text: {raw_answer!r}")
        return {"answer": answer, "citations": citations, "steps": [step]}

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
    final = graph.invoke({"question": question, "flags": [], "steps": []})
    # Redaction runs here, after every Step has seen the original text, so
    # only what is stored changes (ADR-0008). Both fields use classify's
    # matches, the same ones that raised the Flag.
    return {
        "id": str(uuid.uuid4()),
        "event_type": "QueryAnswered",
        "query": redact_query(question, final["pii"]),
        "answer": redact_answer(final["answer"], final["pii"]),
        "flags": final["flags"],
        "steps": final["steps"],
    }
