# Integration test for ChunkRetriever against the isolated regdocs_test
# database, with a fake embedding client and hand-built basis vectors (see
# eval/tests/test_run_eval.py for why that makes ranking exactly predictable).

import psycopg
from regdocs_store.embed import EMBEDDING_DIMENSIONS, EMBEDDING_MODEL, vector_literal
from regdocs_store.testing import (
    DB_URL,
    clean_db,  # noqa: F401
    requires_postgres,
)
from regdocs_track_b.retriever import QUERY_PREFIX, ChunkRetriever

CLAUSE_DOC = "doc-fixture-clauses"


def basis(index: int) -> list[float]:
    vector = [0.0] * EMBEDDING_DIMENSIONS
    vector[index] = 1.0
    return vector


class FakeClient:
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
                "VALUES (%s, 'T', 'P', '2024-01-01', 'https://example.com')",
                (CLAUSE_DOC,),
            )
            cur.executemany(
                "INSERT INTO chunking_generations (id, document_id, chunking_strategy) "
                "VALUES (%s, %s, 'clause_numbered')",
                [
                    (f"{CLAUSE_DOC}-gen-1", CLAUSE_DOC),
                    (f"{CLAUSE_DOC}-gen-2", CLAUSE_DOC),
                ],
            )
            cur.execute(
                "UPDATE documents SET active_chunking_generation_id = %s WHERE id = %s",
                (f"{CLAUSE_DOC}-gen-2", CLAUSE_DOC),
            )
            # c-old is in the inactive generation; it is embedded directly so
            # the test proves the query excludes it, not just the embedder.
            chunks = [
                ("c-1.1", "gen-2", "1.1", "first text", basis(0)),
                ("c-1.2", "gen-2", "1.2", "second text", basis(1)),
                ("c-1.3", "gen-2", "1.3", "third text", basis(2)),
                ("c-old", "gen-1", "2.1", "old text", basis(3)),
            ]
            for chunk_id, gen, locator, text, vector in chunks:
                cur.execute(
                    "INSERT INTO chunks (id, document_id, chunking_generation_id, locator, text) "
                    "VALUES (%s, %s, %s, %s, %s)",
                    (chunk_id, CLAUSE_DOC, f"{CLAUSE_DOC}-{gen}", locator, text),
                )
                cur.execute(
                    "INSERT INTO chunk_embeddings (chunk_id, embedding_model, embedding) "
                    "VALUES (%s, %s, %s)",
                    (chunk_id, EMBEDDING_MODEL, vector_literal(vector)),
                )


def _query_vector() -> list[float]:
    # Ranks c-1.1 > c-1.2 > c-1.3; every other Chunk is at right angles.
    vector = [0.0] * EMBEDDING_DIMENSIONS
    vector[0] = 3.0
    vector[1] = 2.0
    vector[2] = 1.0
    return vector


def _chunk_ids(documents) -> list[str]:
    chunk_ids = []
    for document in documents:
        chunk_ids.append(document.metadata["chunk_id"])
    return chunk_ids


@requires_postgres
def test_returns_top_k_active_chunks_with_metadata(clean_db):  # noqa: F811
    _load_fixture_store()
    client = FakeClient({QUERY_PREFIX + "a question": _query_vector()})
    retriever = ChunkRetriever(db_url=DB_URL, embedding_client=client, k=2)

    documents = retriever.invoke("a question")

    assert client.texts == [QUERY_PREFIX + "a question"]
    assert _chunk_ids(documents) == ["c-1.1", "c-1.2"]
    first = documents[0]
    assert first.page_content == "first text"
    assert first.metadata["document_id"] == CLAUSE_DOC
    assert first.metadata["locator"] == "1.1"
    assert 0.0 < documents[1].metadata["score"] < first.metadata["score"] <= 1.0


@requires_postgres
def test_inactive_generation_chunk_is_never_returned(clean_db):  # noqa: F811
    _load_fixture_store()
    # The query points straight at the inactive-generation Chunk.
    client = FakeClient({QUERY_PREFIX + "old": basis(3)})
    retriever = ChunkRetriever(db_url=DB_URL, embedding_client=client, k=10)

    chunk_ids = _chunk_ids(retriever.invoke("old"))

    assert "c-old" not in chunk_ids
    assert len(chunk_ids) == 3


@requires_postgres
def test_default_k_caps_results_at_five(clean_db):  # noqa: F811
    _load_fixture_store()
    with psycopg.connect(DB_URL) as conn:
        with conn.cursor() as cur:
            for index in range(4, 9):
                chunk_id = f"c-extra-{index}"
                cur.execute(
                    "INSERT INTO chunks (id, document_id, chunking_generation_id, locator, text) "
                    "VALUES (%s, %s, %s, %s, 'extra')",
                    (chunk_id, CLAUSE_DOC, f"{CLAUSE_DOC}-gen-2", f"9.{index}"),
                )
                cur.execute(
                    "INSERT INTO chunk_embeddings (chunk_id, embedding_model, embedding) "
                    "VALUES (%s, %s, %s)",
                    (chunk_id, EMBEDDING_MODEL, vector_literal(basis(index))),
                )
    client = FakeClient({QUERY_PREFIX + "q": _query_vector()})
    retriever = ChunkRetriever(db_url=DB_URL, embedding_client=client)

    assert len(retriever.invoke("q")) == 5
