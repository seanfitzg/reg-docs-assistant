# Opt-in: a real local model must follow the judge's per-claim line format
# (issue #47). The scripted-fake tests prove code computes Confidence and Flags
# from verdict lines; only a real model can show it writes them. Off by
# default because it needs Ollama running with the model pulled; enable with
# RUN_REAL_JUDGE=1.

import os

import pytest
from langchain_ollama import ChatOllama
from regdocs_track_b.graph import answer_question, build_graph
from regdocs_track_b.testing import (
    FakeRetriever,
    RecordingModel,
    make_chunk,
    safe_classifier,
)

pytestmark = pytest.mark.skipif(
    not os.environ.get("RUN_REAL_JUDGE"),
    reason="opt-in: set RUN_REAL_JUDGE=1 (needs Ollama with qwen2.5:7b-instruct)",
)

MODEL = os.environ.get("JUDGE_MODEL") or "qwen2.5:7b-instruct"

CHUNKS = [
    make_chunk(
        "c-1",
        "doc-a",
        "7.1",
        "A firm must give 30 days' written notice before applying a fee waiver.",
        0.80,
    ),
]

# One claim the excerpt states, one it says nothing about.
DRAFT = (
    "A firm must give 30 days' written notice before applying a fee waiver [1]. "
    "Fee waivers are capped at 2% of the balance."
)


def _event():
    graph = build_graph(
        retriever=FakeRetriever(documents=CHUNKS),
        chat_model=RecordingModel(responses=[DRAFT], prompts=[]),
        draft_model_name="fake-chat",
        classifier_model=safe_classifier(),
        classifier_model_name="fake-classifier",
        judge_model=ChatOllama(model=MODEL, temperature=0),
        judge_model_name=MODEL,
    )
    return answer_question(graph, "How much notice before a fee waiver?")


def test_the_real_judge_writes_claim_lines_that_code_can_read():
    event = _event()

    verify = event["steps"][3]
    assert verify["model"] == MODEL
    # Format followed: at least one line parsed, so Confidence isn't the
    # 0.0 that an unreadable reply produces.
    assert verify["confidence"] > 0.0, event
