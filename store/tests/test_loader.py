# Single-seam integration test for loader.py's load_store -- per the seam
# agreed before implementation (/to-spec), this is the *only* test file for
# the loader: no unit tests for upsert SQL or FK-ordering logic in
# isolation, since neither means anything except against a real database
# with its real constraints.
#
# Mirrors ingestion/tests/test_pipeline.py's requires_cp54-style pattern:
# tests that need a real precondition (there, corpus PDFs on disk; here, a
# reachable Postgres) are decorated to *skip*, not fail, when that
# precondition isn't met locally.

import json
import os
from pathlib import Path
from typing import Any

import psycopg
import pytest

from db import DEFAULT_DB_URL
from loader import load_store

# Tests run against a *separate* database (regdocs_test) from the one
# store/README.md's "Loading data" section tells you to load the real
# corpus into (regdocs) -- store/init/002_test_database.sql creates
# regdocs_test with the same schema, empty, specifically so running this
# suite can never wipe out real data you've already loaded. Deriving this
# from DEFAULT_DB_URL (rather than writing out the connection string again)
# means the host/user/password can only ever come from one place -- only
# the database name differs.
DB_URL = os.environ.get(
    "STORE_TEST_DATABASE_URL",
    DEFAULT_DB_URL.rsplit("/", 1)[0] + "/regdocs_test",
)


def _postgres_reachable() -> bool:
    # connect_timeout keeps this fast-failing (default is much longer) --
    # this only needs to answer "is anything listening", not tolerate a
    # slow network.
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
    # @pytest.fixture marks this function as something a test can receive
    # by naming it as a parameter -- every test below takes `clean_db` as
    # an argument, and pytest calls this function automatically before the
    # test body runs.
    #
    # `yield` (instead of `return`) is what splits this function into a
    # "before" half and an "after" half: everything up to `yield` runs
    # before the test, then the test body itself runs, then execution
    # resumes right after `yield` once the test finishes -- whether it
    # passed or failed. The nearest .NET equivalent is a try/finally
    # wrapped around the test, or xUnit's IDisposable.Dispose() convention
    # for per-test cleanup.
    #
    # /store's schema has two circular-ish foreign keys (documents <->
    # chunking_generations, documents.supersedes -> documents itself), so
    # clearing every table between tests has to null those out first --
    # otherwise a DELETE hits "still referenced from table ..." errors.
    # This is test-only teardown, not something loader.py itself ever
    # does -- the loader never deletes anything (ADR-0021). It's also only
    # ever pointed at regdocs_test (DB_URL above), never the real dev
    # database, so this destructive cleanup can't reach real loaded data.
    def _clear():
        with psycopg.connect(DB_URL) as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM chunks")
                cur.execute("UPDATE documents SET active_chunking_generation_id = NULL")
                cur.execute("DELETE FROM chunking_generations")
                cur.execute("UPDATE documents SET supersedes = NULL")
                cur.execute("DELETE FROM documents")

    _clear()
    yield
    _clear()


def _write_fixture_corpus(base: Path) -> tuple[Path, Path]:
    # Builds a small synthetic ingestion/output + manifest.json, in the
    # exact shape ingestion/pipeline.py actually produces (per
    # ingestion/README.md), for one Document that has been re-chunked --
    # i.e. it has *two* Chunking Generations, not just one. The real
    # corpus (as ingested so far) only ever has one Generation per
    # Document, so this is the only way to prove upsert-by-id doesn't
    # collide or overwrite across multiple Generations of the same
    # Document -- an acceptance criterion the real corpus alone can't
    # exercise.
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
                # Active generation is the *second* one -- proves the
                # loader doesn't just always point at whichever Generation
                # happened to be inserted first.
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
    # tmp_path is a *built-in* pytest fixture -- not defined anywhere in
    # this file, the way clean_db is just above. pytest recognizes the
    # parameter name itself and injects a fresh, empty pathlib.Path
    # pointing at a unique temp directory for this one test, deleted
    # automatically afterward. pytest doesn't distinguish "built-in" from
    # "defined in this file" -- both are just fixtures, matched by name.
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
    # Regression test for a bug /code-review caught: chunking_strategy came
    # from manifest.json, looked up fresh on every call to load_store. If a
    # Document were later re-chunked with a *different* strategy and
    # manifest.json's entry updated in place (rather than recording history
    # anywhere), a naive upsert would silently rewrite an existing, already
    # immutable Chunking Generation's recorded strategy on the next loader
    # run -- corrupting a fact ADR-0021's Replay guarantee depends on
    # staying accurate. upsert_immutable's ON CONFLICT DO NOTHING is what
    # prevents this: this test proves it, rather than just asserting the
    # loader "should" be safe.
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
            # Both existing Generations must still show "clause_numbered" --
            # the strategy they were *actually* created with, unaffected by
            # manifest.json's later drift.
            assert cur.fetchall() == [
                ("doc-fixture-doc-gen-1", "clause_numbered"),
                ("doc-fixture-doc-gen-2", "clause_numbered"),
            ]


def _write_two_document_fixture(base: Path, second_supersedes: str | None) -> tuple[Path, Path]:
    # A second, smaller fixture: two Documents, where the second document's
    # `supersedes` can be varied between calls (that's the whole point --
    # proving a second load_store call with a *different* supersedes value
    # for an already-loaded Document doesn't change what's stored).
    output_dir = base / "output"
    (output_dir / "documents").mkdir(parents=True, exist_ok=True)
    (output_dir / "chunks").mkdir(parents=True, exist_ok=True)

    for doc_id, supersedes in (("doc-original", None), ("doc-successor", second_supersedes)):
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
    # Regression test for the same class of bug as
    # test_rerun_never_overwrites_an_existing_generations_strategy, but for
    # documents.supersedes: /code-review caught that phase 3's UPDATE was
    # setting it unconditionally on *every* run, which would silently
    # rewrite an already-loaded Document's supersedes link if the source
    # JSON's value ever changed -- contradicting supersedes' own status as
    # an immutable fact about a Document (CONTEXT.md), the same guarantee
    # upsert_immutable already gives title/publisher/etc.
    output_dir, manifest_path = _write_two_document_fixture(tmp_path, second_supersedes="doc-original")
    load_store(output_dir, manifest_path, DB_URL)

    # Re-run with doc-successor's supersedes changed to point at nothing
    # (None) -- simulating drift in a regenerated Document JSON.
    output_dir, manifest_path = _write_two_document_fixture(tmp_path, second_supersedes=None)
    load_store(output_dir, manifest_path, DB_URL)

    with psycopg.connect(DB_URL) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT supersedes FROM documents WHERE id = 'doc-successor'")
            # Still "doc-original" -- the value from the *first* load,
            # unaffected by the second run's different input.
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


# Mirrors ingestion/tests/test_pipeline.py's requires_full_corpus: the real
# corpus isn't committed to git, so this skips (not fails) unless
# `ingestion/output` has actually been generated locally by running
# ingestion's pipeline first.
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

            # Every Document that has been chunked at all must have its
            # active_chunking_generation_id set -- phase 3 of load_store
            # backfills it for every Document, so none should still be NULL.
            cur.execute(
                "SELECT COUNT(*) FROM documents WHERE active_chunking_generation_id IS NULL"
            )
            assert cur.fetchone() == (0,)
