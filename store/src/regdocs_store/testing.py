# Postgres test helpers shared across the workspace: store's own tests and
# the eval and track-b suites that exercise the same schema.
import json
import os
from pathlib import Path

import psycopg
import pytest

from regdocs_store.db import DEFAULT_DB_URL

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


def write_fixture_corpus(base: Path) -> tuple[Path, Path]:
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
