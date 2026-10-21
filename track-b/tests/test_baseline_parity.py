# Opt-in: the retriever, run over the whole eval dataset against the real
# store with real Ollama embeddings, must reproduce the baseline run report
# (ADR-0032, ADR-0030). Off by default because it needs Postgres loaded and
# embedded plus Ollama running; enable with RUN_BASELINE_PARITY=1.
#
# Compared at k=10, the baseline's k; the retriever's own default is 5.

import json
import os
from pathlib import Path

import pytest

from db import DEFAULT_DB_URL
from embed import OllamaEmbeddingClient
from match import case_hit
from retriever import ChunkRetriever

EVAL_DIR = Path(__file__).parent.parent.parent / "eval"
BASELINE = EVAL_DIR / "runs" / "20260929T111257Z-nomic-embed-text.json"

pytestmark = pytest.mark.skipif(
    not os.environ.get("RUN_BASELINE_PARITY"),
    reason="opt-in: set RUN_BASELINE_PARITY=1 (needs Postgres + Ollama)",
)


def test_recall_at_10_matches_baseline_run_report():
    dataset = json.loads((EVAL_DIR / "dataset.json").read_text(encoding="utf-8"))
    baseline = json.loads(BASELINE.read_text(encoding="utf-8"))
    retriever = ChunkRetriever(
        db_url=os.environ.get("STORE_DATABASE_URL", DEFAULT_DB_URL),
        embedding_client=OllamaEmbeddingClient(),
        k=baseline["config"]["k"],
    )

    hits = 0
    answerable = 0
    for case in dataset["cases"]:
        if case["category"] == "unanswerable":
            continue
        answerable += 1
        chunks = []
        for document in retriever.invoke(case["question"]):
            chunks.append(document.metadata)
        if case_hit(case["gold_locators"], chunks):
            hits += 1

    k = baseline["config"]["k"]
    assert hits / answerable == baseline["summary"]["overall"][f"recall@{k}"]
