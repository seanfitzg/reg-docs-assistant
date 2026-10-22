# Computes a vector embedding for every Chunk in each Document's *active*
# Chunking Generation and stores them in chunk_embeddings.
#
# An embedding is a fixed-length list of numbers (here 768 floats) that a
# neural network produces from text, so that texts with similar *meaning* get
# vectors pointing in similar directions. Retrieval (a later issue) embeds the
# question the same way and asks pgvector for the nearest stored Chunk
# vectors. This script only does the storing half.
#
# Like loader.py, a deliberately standalone step (ADR-0020) that never imports
# from /ingestion.

import os
from typing import Protocol

import psycopg

from regdocs_store.db import DEFAULT_DB_URL, upsert_immutable

# Recorded in chunk_embeddings.embedding_model on every row and part of the
# primary key (ADR-0024): a different model later means new rows alongside
# these, not a replacement. Bare model name only -- version/digest tracking is
# deferred (issue #25's Out of Scope).
EMBEDDING_MODEL = "nomic-embed-text"

# nomic-embed-text's output size; must match store/init/003's vector(768).
EMBEDDING_DIMENSIONS = 768

# nomic-embed-text is trained asymmetrically: stored text is embedded with this
# prefix, search queries with "search_query: ". Skipping it silently degrades
# retrieval and looks like removable noise -- see ADR-0026 before touching.
# Applied only for the embedding call; chunks.text is never modified.
DOCUMENT_PREFIX = "search_document: "

DEFAULT_OLLAMA_HOST = "http://localhost:11434"


class EmbeddingClient(Protocol):
    def embed(self, text: str) -> list[float]: ...


class OllamaEmbeddingClient:
    # Not exercised by the test suite (needs Ollama running with the model
    # pulled); tests inject a fake.
    def __init__(self, host: str = DEFAULT_OLLAMA_HOST, model: str = EMBEDDING_MODEL):
        # Imported lazily so importing embed.py doesn't require `ollama`
        # unless this class is constructed.
        import ollama

        self._client = ollama.Client(host=host)
        self._model = model

    def embed(self, text: str) -> list[float]:
        # One input in, so one vector out: take element [0].
        response = self._client.embed(model=self._model, input=text)
        return list(response["embeddings"][0])


def vector_literal(vector: list[float]) -> str:
    # pgvector accepts '[0.1,0.2,...]' as text and casts it to vector, which
    # avoids needing pgvector's Python adapter for one column. Public because
    # regdocs_eval.run_eval sends its query vectors this way too. str(float)
    # round-trips exactly, so no precision is lost.
    values = ",".join(str(value) for value in vector)
    return "[" + values + "]"


def embed_chunks(db_url: str, client: EmbeddingClient) -> None:
    """Embed every not-yet-embedded Chunk of each Document's active Generation.

    Only Chunks in a Document's `active_chunking_generation_id` are embedded
    (ADR-0025) -- an inactive Generation's Chunks are never retrieval
    candidates, so embedding them would be wasted compute. Chunks that
    already have an embedding for EMBEDDING_MODEL are skipped, so a re-run
    after a crash resumes where it stopped and never recomputes.

    Any failure from `client.embed` propagates immediately -- deliberately
    no try/except. A systemic problem (Ollama not running, model not
    pulled) then shows up on the very first Chunk instead of after working
    through most of the corpus, and re-running is safe because progress is
    saved per Chunk.
    """
    # autocommit, unlike loader.py's single transaction: embedding is slow (one
    # model call per Chunk) and can crash midway, and one big transaction
    # would roll back every embedding already computed.
    with psycopg.connect(db_url, autocommit=True) as conn:
        with conn.cursor() as cur:
            # In scope: Chunks in their Document's active Generation (the
            # join) that have no embedding row for this model (LEFT JOIN ...
            # IS NULL anti-join).
            cur.execute(
                """
                SELECT chunks.id, chunks.text
                FROM chunks
                JOIN documents
                  ON chunks.document_id = documents.id
                 AND chunks.chunking_generation_id = documents.active_chunking_generation_id
                LEFT JOIN chunk_embeddings
                  ON chunk_embeddings.chunk_id = chunks.id
                 AND chunk_embeddings.embedding_model = %(model)s
                WHERE chunk_embeddings.chunk_id IS NULL
                ORDER BY chunks.id
                """,
                {"model": EMBEDDING_MODEL},
            )
            # fetchall() finishes the SELECT before the loop reuses `cur`.
            pending = cur.fetchall()

            for chunk_id, text in pending:
                vector = client.embed(DOCUMENT_PREFIX + text)
                upsert_immutable(
                    cur,
                    "chunk_embeddings",
                    ["chunk_id", "embedding_model", "embedding"],
                    [
                        {
                            "chunk_id": chunk_id,
                            "embedding_model": EMBEDDING_MODEL,
                            "embedding": vector_literal(vector),
                        }
                    ],
                    conflict_columns=["chunk_id", "embedding_model"],
                )


if __name__ == "__main__":
    embed_chunks(
        db_url=os.environ.get("STORE_DATABASE_URL", DEFAULT_DB_URL),
        client=OllamaEmbeddingClient(
            host=os.environ.get("OLLAMA_HOST", DEFAULT_OLLAMA_HOST)
        ),
    )
    print("Embedded active-generation Chunks into /store")
