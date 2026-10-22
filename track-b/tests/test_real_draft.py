# Opt-in: a real local model must follow the citation format (issue #42). The
# scripted-fake tests prove the graph resolves markers correctly; only a real
# model can show it actually writes them. Off by default because it needs
# Ollama running with the model pulled; enable with RUN_REAL_DRAFT=1.

import os

import pytest
from langchain_ollama import ChatOllama

from regdocs_track_b.graph import build_graph
from regdocs_track_b.testing import FakeRetriever, make_chunk

pytestmark = pytest.mark.skipif(
    not os.environ.get("RUN_REAL_DRAFT"),
    reason="opt-in: set RUN_REAL_DRAFT=1 (needs Ollama with qwen2.5:7b-instruct)",
)

MODEL = "qwen2.5:7b-instruct"

CHUNKS = [
    make_chunk("c-1", "doc-a", "4.2", "A firm must keep records for six years.", 0.80),
    make_chunk(
        "c-2",
        "doc-b",
        "7.1",
        "A firm must give 30 days' written notice before applying a fee waiver.",
        0.78,
    ),
    make_chunk(
        "c-3", "doc-c", "9.3", "Complaints must be acknowledged in five days.", 0.70
    ),
]


def test_real_model_cites_the_supporting_chunk_with_a_numbered_marker():
    graph = build_graph(
        retriever=FakeRetriever(documents=CHUNKS),
        chat_model=ChatOllama(model=MODEL, temperature=0),
        draft_model_name=MODEL,
    )

    final = graph.invoke(
        {
            "question": "How much notice must a firm give before applying a fee waiver?",
            "steps": [],
        }
    )

    cited = []
    for citation in final["citations"]:
        cited.append(citation["marker"])
    assert 2 in cited, final["answer"]
