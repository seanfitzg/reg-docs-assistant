# Single-seam integration test for run_eval.py (issue #32): run_eval(db_url,
# client, dataset) -> report, against the isolated regdocs_test database,
# with a fake embedding client and hand-built fixture Chunks/embeddings --
# the same shape as store/tests/test_embed.py. Ollama is never needed.
#
# THE TRICK THAT MAKES THIS DETERMINISTIC: real embeddings are opaque, so
# a test can't predict which Chunk a real question lands nearest to. Here
# every vector is built by hand from "basis" directions (a 1 in one slot,
# 0 everywhere else), so cosine similarity -- and therefore the ranking --
# is known exactly before the query runs:
#   - a query equal to basis(0) has similarity 1.0 with the Chunk stored as
#     basis(0), and 0.0 with every other basis Chunk (they're at right angles);
#   - a query 3*basis(0) + 2*basis(1) + 1*basis(2) ranks those three Chunks
#     in that order, because cosine similarity is proportional to each
#     Chunk's share of the query's direction (3 > 2 > 1).

import json

import psycopg
import pytest

from embed import EMBEDDING_DIMENSIONS, EMBEDDING_MODEL, vector_literal
from run_eval import K, QUERY_PREFIX, run_eval, write_report

# Reused from /store's tests rather than redefined: the isolated
# regdocs_test URL, the skip-if-Postgres-is-down marker, and the per-test
# table-clearing fixture. As in test_embed.py, `clean_db` must be imported
# by name for pytest to find it, even though nothing calls it directly.
from test_loader import DB_URL, clean_db, requires_postgres  # noqa: F401

CLAUSE_DOC = "doc-fixture-clauses"
HEADING_DOC = "doc-fixture-headings"


def basis(index: int, scale: float = 1.0) -> list[float]:
    # A 768-long vector that points purely along one axis. The database
    # column is vector(768), so every fixture vector must be exactly that
    # long or Postgres rejects the INSERT.
    vector = [0.0] * EMBEDDING_DIMENSIONS
    vector[index] = scale
    return vector


def add(*vectors: list[float]) -> list[float]:
    # Element-wise sum: zip(*vectors) walks the vectors in lockstep, one
    # tuple of same-position values at a time (like LINQ's Zip, but over
    # any number of sequences).
    return [
        sum(values)
        for values in zip(*vectors)
    ]


# Every Chunk in the fixture store: (chunk id, document, generation,
# locator, embedding). The last one belongs to a Document's *inactive*
# generation -- it must never be retrieved (ADR-0025), even though one test
# query below points straight at it.
FIXTURE_CHUNKS = [
    ("c-1.1", CLAUSE_DOC, f"{CLAUSE_DOC}-gen-2", "1.1", basis(0)),
    ("c-1.2", CLAUSE_DOC, f"{CLAUSE_DOC}-gen-2", "1.2", basis(1)),
    ("h-intro", HEADING_DOC, f"{HEADING_DOC}-gen-1", "Introduction (p. 2)", basis(2)),
    ("c-old-2.1", CLAUSE_DOC, f"{CLAUSE_DOC}-gen-1", "2.1", basis(3)),
]


class FakeClient:
    # Maps each (prefixed) question to a hand-built vector, and records
    # every text it was asked to embed, so a test can assert the exact
    # string the harness sent -- the ADR-0026 query prefix included.
    def __init__(self, vectors_by_text: dict[str, list[float]]):
        self._vectors = vectors_by_text
        self.texts: list[str] = []

    def embed(self, text: str) -> list[float]:
        self.texts.append(text)
        return self._vectors[text]


def _load_fixture_store():
    with psycopg.connect(DB_URL) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO documents (id, title, publisher, published_date, source_url) "
                "VALUES (%s, 'T', 'P', '2024-01-01', 'https://example.com'), "
                "       (%s, 'T', 'P', '2024-01-01', 'https://example.com')",
                (CLAUSE_DOC, HEADING_DOC),
            )
            cur.executemany(
                "INSERT INTO chunking_generations (id, document_id, chunking_strategy) VALUES (%s, %s, %s)",
                [
                    (f"{CLAUSE_DOC}-gen-1", CLAUSE_DOC, "clause_numbered"),
                    (f"{CLAUSE_DOC}-gen-2", CLAUSE_DOC, "clause_numbered"),
                    (f"{HEADING_DOC}-gen-1", HEADING_DOC, "heading_sections"),
                ],
            )
            # The clause Document's active generation is its *second* one.
            cur.execute(
                "UPDATE documents SET active_chunking_generation_id = id || %s WHERE id = %s",
                ("-gen-2", CLAUSE_DOC),
            )
            cur.execute(
                "UPDATE documents SET active_chunking_generation_id = id || %s WHERE id = %s",
                ("-gen-1", HEADING_DOC),
            )
            for chunk_id, document_id, generation_id, locator, vector in FIXTURE_CHUNKS:
                cur.execute(
                    "INSERT INTO chunks (id, document_id, chunking_generation_id, locator, text) "
                    "VALUES (%s, %s, %s, %s, 'fixture text')",
                    (chunk_id, document_id, generation_id, locator),
                )
                # Embedded directly, even the inactive-generation Chunk
                # (which embed.py itself would skip) -- so the test proves
                # the *retrieval query* excludes it, not just the embedder.
                cur.execute(
                    "INSERT INTO chunk_embeddings (chunk_id, embedding_model, embedding) VALUES (%s, %s, %s)",
                    (chunk_id, EMBEDDING_MODEL, vector_literal(vector)),
                )


def _case(case_id, question, phrasing, category, gold):
    case = {"id": case_id, "question": question, "phrasing": phrasing, "category": category, "gold_locators": gold}
    if category != "unanswerable":
        case["answer_quote"] = "fixture quote"
    return case


DATASET = {
    "dataset_version": 7,
    "cases": [
        # Nearest Chunk is the gold one -> hit at rank 1.
        _case("q01", "rank one", "lexical", "single_passage", [{"document_id": CLAUSE_DOC, "locator": "1.1"}]),
        # Gold is the third-nearest, and a heading_sections Chunk -> hit at
        # rank 3 (which also proves the query returns each Chunk's own
        # strategy: parsing "Introduction (p. 2)" as a clause would raise).
        _case("q02", "rank three", "paraphrase", "single_passage", [{"document_id": HEADING_DOC, "locator": "Introduction (p. 2)"}]),
        # Gold only exists in the inactive generation, and the query points
        # straight at it -> must be a miss, never rank 1.
        _case("q03", "inactive only", "paraphrase", "multi_locator", [{"document_id": CLAUSE_DOC, "locator": "2.1"}]),
        # Unanswerable: no rank, but the top-1 similarity is recorded.
        _case("q04", "nothing to find", "lexical", "unanswerable", []),
    ],
}

QUERY_VECTORS = {
    QUERY_PREFIX + "rank one": basis(0),
    QUERY_PREFIX + "rank three": add(basis(0, 3), basis(1, 2), basis(2, 1)),
    QUERY_PREFIX + "inactive only": basis(3),
    QUERY_PREFIX + "nothing to find": basis(1),
}


@pytest.fixture
def fixture_run(clean_db):
    # Loads the fixture store and runs the harness once per test. Returns a
    # (report, client) tuple -- the client too, so the prefix test can
    # inspect exactly what was sent without a second run. Tests that only
    # need the report unpack it as `report, _ = fixture_run` (`_` is the
    # conventional name for a value you're deliberately ignoring, like C#'s
    # discard `_`).
    _load_fixture_store()
    client = FakeClient(QUERY_VECTORS)
    return run_eval(DB_URL, client, DATASET), client


def _case_result(report, case_id):
    # next(<generator>) returns the first item the generator produces --
    # here, the first case with this id (like LINQ's First(predicate)).
    return next(
        case
        for case in report["cases"]
        if case["id"] == case_id
    )


@requires_postgres
def test_every_question_is_embedded_with_the_query_prefix(fixture_run):
    _, client = fixture_run
    assert QUERY_PREFIX == "search_query: "
    expected_texts = [
        QUERY_PREFIX + case["question"]
        for case in DATASET["cases"]
    ]
    assert client.texts == expected_texts


@requires_postgres
def test_hit_rank_and_similarity_at_the_hit(fixture_run):
    report, _ = fixture_run
    first = _case_result(report, "q01")
    assert first["hit_rank"] == 1
    assert first["hit_similarity"] == pytest.approx(1.0)

    third = _case_result(report, "q02")
    assert third["hit_rank"] == 3
    # cos(query, basis(2)) = 1 / |(3, 2, 1)| = 1 / sqrt(14)
    assert third["hit_similarity"] == pytest.approx(1 / 14**0.5)


@requires_postgres
def test_inactive_generation_chunks_are_never_retrieved(fixture_run):
    report, _ = fixture_run
    missed = _case_result(report, "q03")
    assert missed["hit_rank"] is None
    assert missed["hit_similarity"] is None
    retrieved_ids = {
        (chunk["document_id"], chunk["locator"])
        for chunk in missed["retrieved"]
    }
    assert (CLAUSE_DOC, "2.1") not in retrieved_ids


@requires_postgres
def test_unanswerable_case_records_top1_similarity_and_no_rank(fixture_run):
    report, _ = fixture_run
    unanswerable = _case_result(report, "q04")
    assert unanswerable["hit_rank"] is None
    assert unanswerable["top1_similarity"] == pytest.approx(1.0)
    assert unanswerable["retrieved"][0]["locator"] == "1.2"


@requires_postgres
def test_recall_and_mrr_over_answerable_cases_only(fixture_run):
    report, _ = fixture_run
    summary = report["summary"]
    # Answerable ranks: q01=1, q02=3, q03=miss. q04 (unanswerable) is excluded.
    overall = summary["overall"]
    assert overall["cases"] == 3
    assert overall["recall@1"] == pytest.approx(1 / 3)
    assert overall["recall@3"] == pytest.approx(2 / 3)
    assert overall["recall@5"] == pytest.approx(2 / 3)
    assert overall["recall@10"] == pytest.approx(2 / 3)
    # MRR = mean of 1/rank, with a miss counting 0: (1 + 1/3 + 0) / 3
    assert overall["mrr"] == pytest.approx(4 / 9)

    lexical = summary["by_phrasing"]["lexical"]
    assert lexical["cases"] == 1 and lexical["mrr"] == pytest.approx(1.0)
    paraphrase = summary["by_phrasing"]["paraphrase"]
    assert paraphrase["cases"] == 2
    assert paraphrase["recall@3"] == pytest.approx(0.5)
    assert paraphrase["mrr"] == pytest.approx(1 / 6)

    assert summary["by_category"]["single_passage"]["recall@3"] == pytest.approx(1.0)
    assert summary["by_category"]["multi_locator"]["recall@10"] == pytest.approx(0.0)
    assert "unanswerable" not in summary["by_category"]


@requires_postgres
def test_report_pins_its_configuration(fixture_run):
    report, _ = fixture_run
    config = report["config"]
    assert config["embedding_model"] == EMBEDDING_MODEL
    assert config["query_prefix"] == QUERY_PREFIX
    # A chained comparison: `a == b == c` means `a == b and b == c` (C# has
    # no equivalent). It checks both that the report recorded K and that K
    # is still the 10 the spec asked for.
    assert config["k"] == K == 10
    assert config["dataset_version"] == 7
    assert config["active_chunking_generations"] == {
        CLAUSE_DOC: f"{CLAUSE_DOC}-gen-2",
        HEADING_DOC: f"{HEADING_DOC}-gen-1",
    }


@requires_postgres
def test_an_unembedded_store_fails_loudly_instead_of_scoring_every_case_a_miss(clean_db):
    # clean_db leaves regdocs_test empty: no Chunks, no embeddings. Every
    # search would return nothing, and without a guard every case would
    # quietly score a miss -- a plausible-looking recall of 0.0 caused by
    # a setup mistake (store/embed.py never run), not by retrieval.
    with pytest.raises(RuntimeError, match="store/embed.py"):
        run_eval(DB_URL, FakeClient(QUERY_VECTORS), DATASET)


@requires_postgres
def test_a_dataset_with_no_answerable_cases_is_rejected(fixture_run):
    # Recall and MRR are averages over answerable cases; with none there is
    # nothing to average. That's a broken dataset, so it's refused with a
    # clear message rather than crashing on a division by zero.
    only_unanswerable = {"dataset_version": 1, "cases": [DATASET["cases"][3]]}
    with pytest.raises(ValueError, match="no answerable"):
        run_eval(DB_URL, FakeClient(QUERY_VECTORS), only_unanswerable)


def test_write_report_names_the_file_by_timestamp_and_model_and_never_overwrites(tmp_path):
    # No database needed: this only exercises the file-writing half.
    report_dict = {"created_at": "2026-09-29T10:15:30Z", "config": {"embedding_model": "nomic-embed-text"}}

    path = write_report(report_dict, tmp_path)

    assert path.name == "20260929T101530Z-nomic-embed-text.json"
    assert json.loads(path.read_text(encoding="utf-8")) == report_dict
    with pytest.raises(FileExistsError):
        write_report(report_dict, tmp_path)
