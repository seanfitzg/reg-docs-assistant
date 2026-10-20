# Single-seam integration test for loader.py's load_store -- per the seam
# agreed before implementation (/to-spec), the *only* test file for the
# loader: upsert SQL and FK ordering mean nothing except against a real
# database with its real constraints.
#
# Like ingestion/tests/test_pipeline.py's requires_cp54, tests needing a real
# precondition (here, a reachable Postgres) skip rather than fail when it's
# missing.

import json
import os
from pathlib import Path
from typing import Any

import psycopg
import pytest

from db import DEFAULT_DB_URL
from loader import load_store

# Tests run against a *separate* database (regdocs_test), created empty with
# the same schema by store/init/002_test_database.sql, so the suite can never
# wipe real data loaded into regdocs. Derived from DEFAULT_DB_URL so the
# credentials come from one place; only the database name differs.
DB_URL = os.environ.get(
    "STORE_TEST_DATABASE_URL",
    DEFAULT_DB_URL.rsplit("/", 1)[0] + "/regdocs_test",
)


def _postgres_reachable() -> bool:
    # Short timeout: this only asks "is anything listening".
    try:
        with psycopg.connect(DB_URL, connect_timeout=2):
            return True
    except psycopg.OperationalError:
        return False


requires_postgres = pytest.mark.skipif(
    not _postgres_reachable(),
    reason="Postgres isn't reachable -- run `docker compose up -d` from /store first",
)

REPO_ROOT = Path(__file__).parent.parent.parent
REAL_OUTPUT_DIR = REPO_ROOT / "ingestion" / "output"
REAL_MANIFEST_PATH = REPO_ROOT / "ingestion" / "manifest.json"


@pytest.fixture
def clean_db():
    # The schema has two circular-ish foreign keys (documents <->
    # chunking_generations, documents.supersedes -> documents), so clearing
    # every table has to null those out first or DELETE hits "still
    # referenced" errors. Test-only teardown -- the loader never deletes
    # (ADR-0021) -- and only ever pointed at regdocs_test, never the real dev
    # database.
    def _clear():
        with psycopg.connect(DB_URL) as conn:
            with conn.cursor() as cur:
                # chunk_embeddings references chunks (003), so it has to go
                # first or DELETE FROM chunks hits a foreign-key error.
                cur.execute("DELETE FROM chunk_embeddings")
                cur.execute("DELETE FROM chunks")
                cur.execute("UPDATE documents SET active_chunking_generation_id = NULL")
                cur.execute("DELETE FROM chunking_generations")
                cur.execute("UPDATE documents SET supersedes = NULL")
                cur.execute("DELETE FROM documents")

    _clear()
    yield
    _clear()


def _write_fixture_corpus(base: Path) -> tuple[Path, Path]:
    # A small synthetic ingestion/output + manifest.json, in the shape
    # pipeline.py produces (ingestion/README.md), for one re-chunked Document
    # with *two* Chunking Generations. The real corpus has only one per
    # Document, so this is the only way to prove upsert-by-id doesn't collide
    # or overwrite across Generations of the same Document.
    output_dir = base / "output"
    (output_dir / "documents").mkdir(parents=True, exist_ok=True)
    (output_dir / "chunks").mkdir(parents=True, exist_ok=True)

    document_id = "doc-fixture-doc"
    (output_dir / "documents" / f"{document_id}.json").write_text(
        json.dumps(
            {
                "id": document_id,
                "title": "Fixture Document",
                "publisher": "Test Publisher",
                "published_date": "2024-01-01",
                "source_url": "https://example.com/fixture-doc",
                # The *second* generation is active, proving the loader
                # doesn't just point at the first one inserted.
                "active_chunking_generation_id": f"{document_id}-gen-2",
            }
        ),
        encoding="utf-8",
    )

    chunks = [
        {
            "id": f"{document_id}-gen-1-chunk-001",
            "document_id": document_id,
            "chunking_generation_id": f"{document_id}-gen-1",
            "locator": "1.1",
            "text": "First generation, first chunk.",
        },
        {
            "id": f"{document_id}-gen-2-chunk-001",
            "document_id": document_id,
            "chunking_generation_id": f"{document_id}-gen-2",
            "locator": "1.1",
            "text": "Second generation, first chunk.",
        },
        {
            "id": f"{document_id}-gen-2-chunk-002",
            "document_id": document_id,
            "chunking_generation_id": f"{document_id}-gen-2",
            "locator": "1.2",
            "text": "Second generation, second chunk.",
        },
    ]
    (output_dir / "chunks" / f"{document_id}.json").write_text(
        json.dumps(chunks), encoding="utf-8"
    )

    manifest_path = base / "manifest.json"
    manifest_path.write_text(
        json.dumps(
            [
                {
                    "filename": "fixture-doc.pdf",
                    "title": "Fixture Document",
                    "publisher": "Test Publisher",
                    "published_date": "2024-01-01",
                    "source_url": "https://example.com/fixture-doc",
                    "supersedes": None,
                    "chunking_strategy": "clause_numbered",
                }
            ]
        ),
        encoding="utf-8",
    )

    return output_dir, manifest_path


@requires_postgres
def test_loads_document_with_multiple_generations_without_collision(tmp_path, clean_db):
    output_dir, manifest_path = _write_fixture_corpus(tmp_path)

    load_store(output_dir, manifest_path, DB_URL)

    with psycopg.connect(DB_URL) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id, active_chunking_generation_id FROM documents")
            documents = cur.fetchall()
            assert documents == [("doc-fixture-doc", "doc-fixture-doc-gen-2")]

            cur.execute(
                "SELECT id, document_id, chunking_strategy FROM chunking_generations ORDER BY id"
            )
            generations = cur.fetchall()
            assert generations == [
                ("doc-fixture-doc-gen-1", "doc-fixture-doc", "clause_numbered"),
                ("doc-fixture-doc-gen-2", "doc-fixture-doc", "clause_numbered"),
            ]

            cur.execute(
                "SELECT chunking_generation_id, COUNT(*) FROM chunks GROUP BY chunking_generation_id ORDER BY 1"
            )
            chunk_counts = cur.fetchall()
            assert chunk_counts == [
                ("doc-fixture-doc-gen-1", 1),
                ("doc-fixture-doc-gen-2", 2),
            ]


@requires_postgres
def test_rerunning_the_loader_is_a_safe_no_op(tmp_path, clean_db):
    output_dir, manifest_path = _write_fixture_corpus(tmp_path)

    load_store(output_dir, manifest_path, DB_URL)
    load_store(output_dir, manifest_path, DB_URL)  # same input, second run

    with psycopg.connect(DB_URL) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM documents")
            assert cur.fetchone() == (1,)
            cur.execute("SELECT COUNT(*) FROM chunking_generations")
            assert cur.fetchone() == (2,)
            cur.execute("SELECT COUNT(*) FROM chunks")
            assert cur.fetchone() == (3,)


@requires_postgres
def test_rerun_never_overwrites_an_existing_generations_strategy(tmp_path, clean_db):
    # Regression test for a bug /code-review caught: chunking_strategy is read
    # from manifest.json on every load_store call. If a Document were
    # re-chunked with a different strategy and its manifest entry updated in
    # place, a naive upsert would rewrite an immutable Chunking Generation's
    # recorded strategy, corrupting a fact ADR-0021's Replay guarantee
    # depends on. upsert_immutable's ON CONFLICT DO NOTHING prevents it.
    output_dir, manifest_path = _write_fixture_corpus(tmp_path)
    load_store(output_dir, manifest_path, DB_URL)

    # Simulate manifest.json drifting after the fact -- same document,
    # same filename, but a different chunking_strategy recorded now.
    manifest_path.write_text(
        json.dumps(
            [
                {
                    "filename": "fixture-doc.pdf",
                    "title": "Fixture Document",
                    "publisher": "Test Publisher",
                    "published_date": "2024-01-01",
                    "source_url": "https://example.com/fixture-doc",
                    "supersedes": None,
                    "chunking_strategy": "heading_sections",
                }
            ]
        ),
        encoding="utf-8",
    )
    load_store(output_dir, manifest_path, DB_URL)

    with psycopg.connect(DB_URL) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, chunking_strategy FROM chunking_generations ORDER BY id"
            )
            # Still "clause_numbered", the strategy they were created with,
            # unaffected by the manifest's later drift.
            assert cur.fetchall() == [
                ("doc-fixture-doc-gen-1", "clause_numbered"),
                ("doc-fixture-doc-gen-2", "clause_numbered"),
            ]


def _write_two_document_fixture(
    base: Path, second_supersedes: str | None
) -> tuple[Path, Path]:
    # Two Documents, where the second's `supersedes` varies between calls, to
    # prove a second load with a different value for an already-loaded
    # Document doesn't change what's stored.
    output_dir = base / "output"
    (output_dir / "documents").mkdir(parents=True, exist_ok=True)
    (output_dir / "chunks").mkdir(parents=True, exist_ok=True)

    for doc_id, supersedes in (
        ("doc-original", None),
        ("doc-successor", second_supersedes),
    ):
        document: dict[str, Any] = {
            "id": doc_id,
            "title": f"Fixture {doc_id}",
            "publisher": "Test Publisher",
            "published_date": "2024-01-01",
            "source_url": f"https://example.com/{doc_id}",
        }
        if supersedes is not None:
            document["supersedes"] = supersedes
        (output_dir / "documents" / f"{doc_id}.json").write_text(
            json.dumps(document), encoding="utf-8"
        )
        (output_dir / "chunks" / f"{doc_id}.json").write_text("[]", encoding="utf-8")

    manifest_path = base / "manifest.json"
    manifest_path.write_text(
        json.dumps(
            [
                {
                    "filename": "original.pdf",
                    "title": "Fixture doc-original",
                    "publisher": "Test Publisher",
                    "published_date": "2024-01-01",
                    "source_url": "https://example.com/doc-original",
                    "supersedes": None,
                    "chunking_strategy": "clause_numbered",
                },
                {
                    "filename": "successor.pdf",
                    "title": "Fixture doc-successor",
                    "publisher": "Test Publisher",
                    "published_date": "2024-01-01",
                    "source_url": "https://example.com/doc-successor",
                    "supersedes": second_supersedes,
                    "chunking_strategy": "clause_numbered",
                },
            ]
        ),
        encoding="utf-8",
    )
    return output_dir, manifest_path


@requires_postgres
def test_supersedes_is_set_once_and_never_overwritten(tmp_path, clean_db):
    # Same class of bug as
    # test_rerun_never_overwrites_an_existing_generations_strategy, for
    # documents.supersedes: /code-review caught that phase 3's UPDATE set it
    # on *every* run, which would rewrite an already-loaded Document's link if
    # the source JSON changed, contradicting its immutability (CONTEXT.md).
    output_dir, manifest_path = _write_two_document_fixture(
        tmp_path, second_supersedes="doc-original"
    )
    load_store(output_dir, manifest_path, DB_URL)

    # Re-run with doc-successor's supersedes dropped, simulating drift in
    # regenerated Document JSON.
    output_dir, manifest_path = _write_two_document_fixture(
        tmp_path, second_supersedes=None
    )
    load_store(output_dir, manifest_path, DB_URL)

    with psycopg.connect(DB_URL) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT supersedes FROM documents WHERE id = 'doc-successor'")
            # Still the value from the *first* load.
            assert cur.fetchone() == ("doc-original",)


@requires_postgres
def test_invalid_chunking_strategy_raises_a_clear_error(tmp_path, clean_db):
    output_dir, manifest_path = _write_fixture_corpus(tmp_path)
    manifest_path.write_text(
        json.dumps(
            [
                {
                    "filename": "fixture-doc.pdf",
                    "title": "Fixture Document",
                    "publisher": "Test Publisher",
                    "published_date": "2024-01-01",
                    "source_url": "https://example.com/fixture-doc",
                    "supersedes": None,
                    "chunking_strategy": "clause_numbred",  # typo
                }
            ]
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="clause_numbred"):
        load_store(output_dir, manifest_path, DB_URL)


# Like test_pipeline.py's requires_full_corpus: the real corpus isn't in git,
# so skip unless ingestion/output has been generated locally.
requires_ingested_corpus = pytest.mark.skipif(
    not (REAL_OUTPUT_DIR / "documents").is_dir(),
    reason="ingestion/output isn't present -- run ingestion's pipeline first (see ingestion/README.md)",
)


@requires_postgres
@requires_ingested_corpus
def test_loads_the_full_ingested_corpus(clean_db):
    load_store(REAL_OUTPUT_DIR, REAL_MANIFEST_PATH, DB_URL)

    expected_document_count = len(list((REAL_OUTPUT_DIR / "documents").glob("*.json")))
    expected_chunk_count = sum(
        len(json.loads(path.read_text(encoding="utf-8")))
        for path in (REAL_OUTPUT_DIR / "chunks").glob("*.json")
    )

    with psycopg.connect(DB_URL) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM documents")
            assert cur.fetchone() == (expected_document_count,)

            cur.execute("SELECT COUNT(*) FROM chunks")
            assert cur.fetchone() == (expected_chunk_count,)

            # Phase 3 sets it for every Document, so none should be NULL.
            cur.execute(
                "SELECT COUNT(*) FROM documents WHERE active_chunking_generation_id IS NULL"
            )
            assert cur.fetchone() == (0,)
