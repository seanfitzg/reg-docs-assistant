# Single-seam integration test for embed.py's embed_chunks, mirroring
# test_loader.py: real (isolated) Postgres, no Ollama. The embedding call
# goes through an injectable client (EmbeddingClient), so these tests hand
# embed_chunks a *fake* client instead of a real Ollama-backed one -- the
# same idea as injecting an interface implementation in a .NET test instead
# of the real service, just without needing a mocking library: Python's
# "duck typing" means any object with an `embed(text)` method qualifies.

import psycopg
import pytest

from embed import DOCUMENT_PREFIX, EMBEDDING_DIMENSIONS, EMBEDDING_MODEL, embed_chunks
from loader import load_store

# Reused (not redefined) from test_loader.py: the same isolated
# regdocs_test database, skip-if-Postgres-is-down decorator, per-test
# cleanup fixture (extended to clear chunk_embeddings), and the fixture
# corpus with one Document that has TWO Chunking Generations (gen-1
# inactive with 1 chunk, gen-2 active with 2 chunks) -- exactly the shape
# the active-generation-only rule (ADR-0025) needs to be exercised.
# `clean_db` looks unused here but pytest finds fixtures by *name in the
# module namespace*, so importing it is what makes it available.
from test_loader import DB_URL, _write_fixture_corpus, clean_db, requires_postgres  # noqa: F401

ACTIVE_CHUNK_TEXTS = ["Second generation, first chunk.", "Second generation, second chunk."]


class RecordingClient:
    # A test double that records every text it was asked to embed, so tests
    # can assert on the *exact* string embed_chunks sent -- not merely that
    # some embedding came back. Returns a fixed-length vector of the right
    # dimensionality, because the database column is vector(768) and would
    # reject anything else.
    def __init__(self, fail_on_call: int | None = None):
        self.texts: list[str] = []
        self._fail_on_call = fail_on_call

    def embed(self, text: str) -> list[float]:
        # len(self.texts) + 1 is this call's 1-based number, counted before
        # the text is recorded.
        if self._fail_on_call == len(self.texts) + 1:
            raise RuntimeError("simulated Ollama failure")
        self.texts.append(text)
        return [0.5] * EMBEDDING_DIMENSIONS


def _load_fixture(tmp_path):
    output_dir, manifest_path = _write_fixture_corpus(tmp_path)
    load_store(output_dir, manifest_path, DB_URL)


def _embedded_chunk_ids() -> list[str]:
    with psycopg.connect(DB_URL) as conn:
        rows = conn.execute(
            "SELECT chunk_id FROM chunk_embeddings ORDER BY chunk_id"
        ).fetchall()
    return [row[0] for row in rows]


@requires_postgres
def test_embeds_only_chunks_of_the_active_generation(tmp_path, clean_db):
    _load_fixture(tmp_path)
    client = RecordingClient()

    embed_chunks(DB_URL, client)

    # gen-1 (inactive) chunk is absent; both gen-2 (active) chunks are present.
    assert _embedded_chunk_ids() == [
        "doc-fixture-doc-gen-2-chunk-001",
        "doc-fixture-doc-gen-2-chunk-002",
    ]
    assert len(client.texts) == 2  # the inactive chunk cost no embedding call
    with psycopg.connect(DB_URL) as conn:
        # Every row is tagged with the model name, so a future second model
        # can coexist alongside these (ADR-0024).
        models = conn.execute("SELECT DISTINCT embedding_model FROM chunk_embeddings").fetchall()
        assert models == [(EMBEDDING_MODEL,)]


@requires_postgres
def test_text_is_prefixed_for_the_model_but_stored_raw(tmp_path, clean_db):
    _load_fixture(tmp_path)
    client = RecordingClient()

    embed_chunks(DB_URL, client)

    # The client saw the prefixed text (ADR-0026)...
    assert sorted(client.texts) == sorted(DOCUMENT_PREFIX + text for text in ACTIVE_CHUNK_TEXTS)
    assert DOCUMENT_PREFIX == "search_document: "
    # ...but chunks.text itself was never modified.
    with psycopg.connect(DB_URL) as conn:
        stored = conn.execute(
            "SELECT text FROM chunks WHERE chunking_generation_id = 'doc-fixture-doc-gen-2' ORDER BY id"
        ).fetchall()
    assert [row[0] for row in stored] == ACTIVE_CHUNK_TEXTS


@requires_postgres
def test_rerun_does_not_recompute_existing_embeddings(tmp_path, clean_db):
    _load_fixture(tmp_path)
    embed_chunks(DB_URL, RecordingClient())

    second_client = RecordingClient()
    embed_chunks(DB_URL, second_client)

    assert second_client.texts == []  # nothing left to embed, so no calls at all
    assert len(_embedded_chunk_ids()) == 2  # and no duplicates or errors


@requires_postgres
def test_failure_stops_the_run_loudly_and_a_rerun_resumes(tmp_path, clean_db):
    _load_fixture(tmp_path)

    # The second embedding call blows up. embed_chunks must NOT swallow it...
    with pytest.raises(RuntimeError, match="simulated Ollama failure"):
        embed_chunks(DB_URL, RecordingClient(fail_on_call=2))

    # ...and the first chunk's embedding, computed before the crash, must
    # already be saved (committed per chunk, not in one all-or-nothing
    # transaction) -- otherwise a crash would throw away all progress.
    assert len(_embedded_chunk_ids()) == 1

    # A plain re-run picks up where it left off: only the missing chunk.
    resume_client = RecordingClient()
    embed_chunks(DB_URL, resume_client)
    assert len(resume_client.texts) == 1
    assert len(_embedded_chunk_ids()) == 2
