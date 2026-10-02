# The retrieval eval harness (issue #32): asks the vector store every Eval
# Case's question, scores what comes back against the case's Gold Locators,
# and writes an immutable run report.
#
# WHAT'S BEING MEASURED: retrieval only -- "did the right Chunk come back
# near the top?" -- not answer quality. No LLM writes an answer here. The
# retriever is deliberately minimal and throwaway (issue #32's
# Implementation Decisions): its job is to produce a *baseline* that the
# later .NET retriever must reproduce on the same embeddings. If .NET
# scores lower on identical data, that points at a bug (a missing query
# prefix, a wrong distance operator), not at the model.
#
# Run:  python eval/run_eval.py   (see eval/README.md for prerequisites)

import json
import os
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import psycopg

EVAL_DIR = Path(__file__).parent
# Reuse /store's connection default and embedding client instead of
# duplicating them (issue #32). /store isn't an installable package, so --
# the same trick the test conftest files use -- its folder goes on
# sys.path, after which "from db import ..." finds store/db.py.
sys.path.insert(0, str(EVAL_DIR.parent / "store"))

from db import DEFAULT_DB_URL  # noqa: E402  (import must follow the sys.path edit)
from embed import (  # noqa: E402
    DEFAULT_OLLAMA_HOST,
    EMBEDDING_MODEL,
    EmbeddingClient,
    OllamaEmbeddingClient,
    vector_literal,
)
from match import case_hit  # noqa: E402

# The *query* half of nomic-embed-text's asymmetric convention (ADR-0026).
# store/embed.py stored every Chunk as "search_document: <text>"; a question
# must be sent as "search_query: <text>" so the model places it in the
# same space the way it was trained to. Leaving it off still "works" --
# vectors come back, results come back -- it just quietly scores worse,
# which is exactly the kind of bug this baseline exists to catch.
QUERY_PREFIX = "search_query: "

# How many Chunks retrieval returns per question ("top-k").
K = 10

# Recall is reported at each of these cut-offs: Recall@3 = "fraction of
# answerable questions whose first correct Chunk was in the top 3".
RECALL_CUTOFFS = (1, 3, 5, 10)

DEFAULT_DATASET = EVAL_DIR / "dataset.json"
DEFAULT_RUNS_DIR = EVAL_DIR / "runs"

# The retrieval query -- the whole retriever is this one statement.
#
# `<=>` is pgvector's COSINE DISTANCE operator: 0 when two vectors point the
# same way, 1 when they're at right angles (unrelated), 2 when opposite.
# Cosine looks only at *direction*, not length, which is what embeddings
# encode meaning in. `1 - distance` turns it back into cosine SIMILARITY
# (1 = same meaning), the more intuitive number to report.
#
# ORDER BY distance ... LIMIT k is "nearest-neighbour search". With no
# vector index on chunk_embeddings this is an EXACT search: Postgres
# computes the distance to every row (~2,000 here -- trivial) and sorts.
# An approximate index (ivfflat/hnsw) would be faster at scale but can
# miss true neighbours, and that loss would contaminate the measurement.
#
# The JOIN to documents on active_chunking_generation_id restricts the
# search to each Document's active Chunking Generation (ADR-0025), and the
# JOIN to chunking_generations supplies each Chunk's chunking_strategy,
# which the match rule needs to parse its locator (ADR-0028).
#
# %(query)s::vector: the question's vector arrives as pgvector's text form
# '[0.1,0.2,...]' and ::vector casts it. It's used twice, so it's a named
# parameter. chunks.id is a tie-breaker, so equal distances always come
# back in the same order and a re-run can't reshuffle ranks.
RETRIEVAL_SQL = """
    SELECT chunks.document_id,
           chunks.locator,
           chunking_generations.chunking_strategy,
           1 - (chunk_embeddings.embedding <=> %(query)s::vector) AS similarity
    FROM chunk_embeddings
    JOIN chunks
      ON chunks.id = chunk_embeddings.chunk_id
    JOIN documents
      ON documents.id = chunks.document_id
     AND documents.active_chunking_generation_id = chunks.chunking_generation_id
    JOIN chunking_generations
      ON chunking_generations.id = chunks.chunking_generation_id
    WHERE chunk_embeddings.embedding_model = %(model)s
    ORDER BY chunk_embeddings.embedding <=> %(query)s::vector, chunks.id
    LIMIT %(k)s
"""


def _retrieve(cur: psycopg.Cursor, query_vector: list[float]) -> list[dict]:
    cur.execute(
        RETRIEVAL_SQL,
        {"query": vector_literal(query_vector), "model": EMBEDDING_MODEL, "k": K},
    )
    rows = cur.fetchall()
    if not rows:
        # Vector search always returns its nearest neighbours when there
        # are any, so nothing at all means there's nothing to search -- the
        # store isn't loaded or embedded. Carrying on would score every
        # case a miss: a plausible-looking 0.0 caused by setup, not by
        # retrieval, which is exactly the silent failure ADR-0028 forbids.
        raise RuntimeError(
            f"no {EMBEDDING_MODEL} Chunk Embeddings to search -- load the store and run store/embed.py first"
        )
    # Each row is a tuple in SELECT order; turning it into a dict gives the
    # {"document_id", "locator", "chunking_strategy"} shape match.case_hit
    # expects, plus the similarity score.
    return [
        {
            "document_id": document_id,
            "locator": locator,
            "chunking_strategy": strategy,
            "similarity": similarity,
        }
        for document_id, locator, strategy, similarity in rows
    ]


def _active_generations(cur: psycopg.Cursor) -> dict[str, str]:
    # Every Document's active Chunking Generation at run time, pinned into
    # the report (ADR-0030): re-chunking a Document later changes what
    # retrieval can return, so a score is only comparable to another run's
    # if both searched the same generations.
    cur.execute("SELECT id, active_chunking_generation_id FROM documents ORDER BY id")
    # fetchall() returns a list of 2-tuples (id, generation id); dict()
    # turns a sequence of (key, value) pairs straight into a dictionary --
    # like LINQ's ToDictionary(t => t.Item1, t => t.Item2).
    return dict(cur.fetchall())


def _score_case(case: dict, retrieved: list[dict]) -> dict:
    gold = case["gold_locators"]
    # Every retrieved Chunk is checked on its own, in rank order.
    # enumerate(..., start=1) yields (1, first), (2, second), ... -- a
    # 1-based rank. Checking *all* of them (not stopping at the first hit)
    # matters: case_hit also validates each Chunk's locator, raising on one
    # it can't parse (ADR-0028) instead of letting it score a silent miss.

    # hit_ranks = [rank for rank, chunk in enumerate(retrieved, start=1) if case_hit(gold, [chunk])]
    hit_ranks = []
    for rank, chunk in enumerate(retrieved, start=1):
        # case_hit takes a list of Chunks, so wrap this one in a
        # single-element list to ask "is *this* Chunk a gold hit?"
        if case_hit(gold, [chunk]):
            hit_ranks.append(rank)
    # The first hit is the one that counts; a multi_locator case may have
    # several gold Chunks in the top k, but recall and MRR only care how
    # soon the first appears.
    # An empty list is falsy in Python, so "if hit_ranks" means "if there
    # was at least one hit".
    if hit_ranks:
        hit_rank = hit_ranks[0]
    else:
        hit_rank = None

    result = {
        "id": case["id"],
        "phrasing": case["phrasing"],
        "category": case["category"],
        "hit_rank": hit_rank,
        # The full top-k, kept so a later reader (or the .NET retriever's
        # comparison) can see *what* came back, not just whether it hit.
        "retrieved": [
            {
                "document_id": c["document_id"],
                "locator": c["locator"],
                "similarity": c["similarity"],
            }
            for c in retrieved
        ],
    }
    if case["category"] == "unanswerable":
        # Nothing can be a hit, so record how confident the *best wrong*
        # match looked. Vector search always returns its nearest neighbours
        # -- there's no "0 results" -- so this score is the only signal a
        # future similarity threshold could use to say "not in the corpus".
        # (_retrieve guarantees at least one Chunk, so [0] always exists.)
        result["top1_similarity"] = retrieved[0]["similarity"]
    else:
        if hit_rank:
            # hit_rank is 1-based but list indexes are 0-based, hence the - 1.
            result["hit_similarity"] = retrieved[hit_rank - 1]["similarity"]
        else:
            result["hit_similarity"] = None
    return result


def _metrics(ranks: list[int | None]) -> dict:
    # ranks: one entry per answerable case -- its 1-based hit rank, or None
    # for a miss.
    #
    # RECALL@k: the fraction of cases whose correct Chunk appeared anywhere
    # in the top k. Easy to read ("7 of 10 found in the top 3") but blind to
    # *where* within those k it landed.
    #
    # MRR (Mean Reciprocal Rank): average of 1/rank, with a miss counting 0.
    # Rank 1 scores 1.0, rank 2 scores 0.5, rank 10 scores 0.1 -- so it
    # rewards putting the right Chunk *first*, which matters because the
    # LLM reads the top Chunks first and may only be given a few of them.
    count = len(ranks)
    metrics = {"cases": count}
    for cutoff in RECALL_CUTOFFS:
        # sum() over a generator of booleans counts the Trues (True == 1).
        hits_within_cutoff = sum(r is not None and r <= cutoff for r in ranks)
        metrics[f"recall@{cutoff}"] = hits_within_cutoff / count
    reciprocal_rank_total = sum(1 / r for r in ranks if r is not None)
    metrics["mrr"] = reciprocal_rank_total / count
    return metrics


def _summarise(case_results: list[dict]) -> dict:
    # Unanswerable cases are excluded from every metric (ADR-0029): they
    # have no Gold Locators, so "recall" means nothing for them and counting
    # them as misses would drag every score down for the wrong reason.
    answerable = [c for c in case_results if c["category"] != "unanswerable"]
    if not answerable:
        # Every metric is an average over answerable cases; with none there
        # is nothing to average (and _metrics would divide by zero). A
        # dataset like that is a mistake, so say so plainly.
        raise ValueError(
            "the dataset has no answerable cases, so recall and MRR are undefined"
        )

    def grouped(field: str) -> dict:
        # defaultdict(list) creates an empty list the first time a key is
        # touched -- like a Dictionary<string, List<int?>> with GetOrAdd.
        groups = defaultdict(list)
        for case in answerable:
            groups[case[field]].append(case["hit_rank"])
        return {key: _metrics(ranks) for key, ranks in sorted(groups.items())}

    overall_ranks = [c["hit_rank"] for c in answerable]
    return {
        "overall": _metrics(overall_ranks),
        # Reported separately to expose lexical-overlap bias (ADR-0029): if
        # paraphrase recall is far below lexical, retrieval is leaning on
        # shared words more than on meaning.
        "by_phrasing": grouped("phrasing"),
        "by_category": grouped("category"),
    }


def run_eval(db_url: str, client: EmbeddingClient, dataset: dict) -> dict:
    """Run every Eval Case in `dataset` through retrieval and return a report.

    The single seam the integration test drives: real Postgres in, report
    dict out. Writing the report to disk is write_report's job, kept
    separate so this stays free of file-system side effects.
    """
    # Embed every question first, before touching the database. A systemic
    # Ollama problem then fails on the first question, and the database
    # transaction below isn't held open across slow model calls.
    query_vectors = [
        client.embed(QUERY_PREFIX + case["question"]) for case in dataset["cases"]
    ]

    with psycopg.connect(db_url) as conn:
        # REPEATABLE READ: every query in this transaction sees one frozen
        # snapshot of the database, so the active generations pinned into
        # the report are guaranteed to be the ones every search ran
        # against -- even if someone re-loads the store mid-run. read_only
        # documents (and enforces) that the harness never writes.
        # Both must be set before the transaction's first statement.
        conn.isolation_level = psycopg.IsolationLevel.REPEATABLE_READ
        conn.read_only = True
        with conn.cursor() as cur:
            active_generations = _active_generations(cur)
            case_results = []
            # zip pairs each case with its query vector, in lockstep.
            for case, query_vector in zip(dataset["cases"], query_vectors):
                retrieved = _retrieve(cur, query_vector)
                case_results.append(_score_case(case, retrieved))

    return {
        # Seconds precision, UTC, ISO-8601 -- also the basis of the file name.
        "created_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        # Everything that could change the scores, pinned (ADR-0030), so two
        # reports are only ever compared like-for-like.
        "config": {
            "embedding_model": EMBEDDING_MODEL,
            "query_prefix": QUERY_PREFIX,
            "k": K,
            "dataset_version": dataset["dataset_version"],
            "active_chunking_generations": active_generations,
        },
        "summary": _summarise(case_results),
        "cases": case_results,
    }


def write_report(report: dict, runs_dir: Path = DEFAULT_RUNS_DIR) -> Path:
    """Write `report` to runs_dir/<UTC timestamp>-<model>.json; never overwrite.

    Run reports are immutable once written (ADR-0030) -- a later run is a
    new file beside the old ones, the way a new event is appended rather
    than an old one edited.
    """
    # "2026-09-29T10:15:30Z" -> "20260929T101530Z": the same instant with
    # the characters Windows file names dislike (":") removed.
    stamp = report["created_at"].replace("-", "").replace(":", "")
    path = runs_dir / f"{stamp}-{report['config']['embedding_model']}.json"
    runs_dir.mkdir(parents=True, exist_ok=True)
    # Mode "x" is exclusive creation: open fails with FileExistsError if the
    # file already exists, atomically -- no check-then-write race window.
    with path.open("x", encoding="utf-8") as f:
        # indent=2 pretty-prints, so a committed report diffs readably.
        # ensure_ascii=False writes characters like the curly quotes in some
        # locators as themselves, instead of \u201c-style escapes.
        json.dump(report, f, indent=2, ensure_ascii=False)
        # json.dump doesn't end with a newline; git and most editors expect one.
        f.write("\n")
    return path


def format_summary(report: dict) -> str:
    """A small human-readable table of the report's summary, for the console."""
    # Format specs after the colon in an f-string control layout, like C#'s
    # alignment/format components ({value,-26} / {value,7:F2}):
    #   :<26   left-align in a 26-character column   (C# {x,-26})
    #   :>4    right-align in a 4-character column   (C# {x,4})
    #   :>7.2f right-align in 7 characters, as a float with 2 decimals (C# {x,7:F2})
    recall_headers = "".join(f"{'R@' + str(c):>7}" for c in RECALL_CUTOFFS)
    header = f"{'group':<26}{'n':>4}" + recall_headers + f"{'MRR':>7}"
    lines = [header, "-" * len(header)]

    def row(label: str, m: dict) -> str:
        # f"{m[f'recall@{c}']:>7.2f}" nests one f-string inside another: the
        # inner one builds the key ("recall@3"), the outer one looks it up
        # and formats the value. The inner uses single quotes so it doesn't
        # end the outer double-quoted string.
        recalls = "".join(f"{m[f'recall@{c}']:>7.2f}" for c in RECALL_CUTOFFS)
        return f"{label:<26}{m['cases']:>4}{recalls}{m['mrr']:>7.2f}"

    summary = report["summary"]
    lines.append(row("overall", summary["overall"]))
    for key, metrics in summary["by_phrasing"].items():
        lines.append(row(f"phrasing={key}", metrics))
    for key, metrics in summary["by_category"].items():
        lines.append(row(f"category={key}", metrics))

    unanswerable = [
        c
        for c in report["cases"]
        if c["category"] == "unanswerable"  # keep only the unanswerable cases
    ]
    if unanswerable:
        lines.append("")
        lines.append("unanswerable (top-1 similarity -- no threshold applied):")
        for case in unanswerable:
            lines.append(f"  {case['id']}: {case['top1_similarity']:.3f}")
    return "\n".join(lines)


if __name__ == "__main__":
    dataset = json.loads(DEFAULT_DATASET.read_text(encoding="utf-8"))
    report = run_eval(
        db_url=os.environ.get("STORE_DATABASE_URL", DEFAULT_DB_URL),
        client=OllamaEmbeddingClient(
            host=os.environ.get("OLLAMA_HOST", DEFAULT_OLLAMA_HOST)
        ),
        dataset=dataset,
    )
    path = write_report(report)
    print(format_summary(report))
    print(f"\nReport written to {path}")
