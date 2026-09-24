# Computes a vector embedding for every Chunk in each Document's *active*
# Chunking Generation and stores them in chunk_embeddings.
#
# WHAT AN EMBEDDING IS: a fixed-length list of numbers (here 768 floats)
# that a neural network produces from a piece of text, arranged so that
# texts with similar *meaning* end up as vectors pointing in similar
# directions. Retrieval (a later issue) embeds the user's question the same
# way and asks Postgres/pgvector "which stored Chunk vectors are nearest to
# this one?" -- semantic search, rather than keyword matching. This script
# only does the storing half: it never searches.
#
# Like loader.py, a deliberately standalone step (ADR-0020), and it never
# imports from /ingestion (/store has its own venv).

import os
from typing import Protocol

import psycopg

from db import DEFAULT_DB_URL, upsert_immutable

# Recorded in chunk_embeddings.embedding_model on every row. Part of the
# primary key (ADR-0024): a different model later means different rows
# alongside these, not a replacement. Bare model name only -- version/digest
# tracking is a deliberately deferred gap (issue #25's Out of Scope).
EMBEDDING_MODEL = "nomic-embed-text"

# nomic-embed-text's output size; must match store/init/003's vector(768).
EMBEDDING_DIMENSIONS = 768

# nomic-embed-text is trained *asymmetrically*: text stored for later
# retrieval is embedded with this prefix, and a search query (a later issue)
# with "search_query: " instead. Skipping it silently degrades retrieval
# quality, and it looks like removable noise -- see ADR-0026 before touching.
# Applied only for the instant of the embedding call; chunks.text is never
# modified.
DOCUMENT_PREFIX = "search_document: "

DEFAULT_OLLAMA_HOST = "http://localhost:11434"


class EmbeddingClient(Protocol):
    # A typing.Protocol is Python's structural interface: any object that
    # has a matching `embed` method counts as an EmbeddingClient -- it never
    # has to declare "implements EmbeddingClient" the way a C# class would
    # declare `: IEmbeddingClient`. That's why tests can pass a tiny fake
    # class with no shared base type at all.
    def embed(self, text: str) -> list[float]: ...


class OllamaEmbeddingClient:
    # The real client: calls a local Ollama server's HTTP API through the
    # official `ollama` Python package. Not exercised by the test suite (it
    # needs Ollama running and the model pulled) -- tests inject a fake.
    def __init__(self, host: str = DEFAULT_OLLAMA_HOST, model: str = EMBEDDING_MODEL):
        # Imported here, not at the top of the file, so importing embed.py
        # (e.g. from tests) never requires the `ollama` package unless this
        # class is actually constructed.
        import ollama

        self._client = ollama.Client(host=host)
        self._model = model

    def embed(self, text: str) -> list[float]:
        # ollama's embed() accepts one string or a list of strings and
        # returns `.embeddings`: one vector per input. One input in, so
        # take element [0].
        response = self._client.embed(model=self._model, input=text)
        return list(response["embeddings"][0])


def _vector_literal(vector: list[float]) -> str:
    # pgvector accepts a vector as text in the form '[0.1,0.2,...]', which
    # Postgres casts to the vector type on insert. Sending it as that string
    # avoids needing pgvector's own Python adapter package for one column.
    return "[" + ",".join(str(value) for value in vector) + "]"


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
    # autocommit=True: every statement commits immediately, instead of the
    # whole run being one transaction (as loader.py's is). That's the
    # opposite choice from loader.py, on purpose: embedding is slow (one
    # model call per Chunk) and can crash midway, and with one big
    # transaction a crash would roll back *every* embedding already
    # computed. Committing per Chunk keeps the work done so far.
    with psycopg.connect(db_url, autocommit=True) as conn:
        with conn.cursor() as cur:
            # In scope = Chunks belonging to their Document's active
            # Generation (the join condition), that don't yet have an
            # embedding row for this model (LEFT JOIN ... IS NULL: "no
            # matching row on the right side" -- the SQL anti-join, the
            # set-difference cousin of LINQ's Except).
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
            # fetchall() pulls the whole (id, text) list into memory before
            # the loop starts, so the SELECT's cursor is finished with
            # before the loop below reuses `cur` for INSERTs.
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
                            "embedding": _vector_literal(vector),
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
