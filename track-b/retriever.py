# Track B's retriever (ADR-0032): a LangChain retriever over the existing
# chunk_embeddings table, not LangChain's own PGVector integration.
#
# A LangChain *retriever* is anything that turns a question string into a list
# of `Document`s. Downstream pieces (the later draft Step, LangGraph nodes)
# depend only on that interface, so swapping in a hybrid keyword-plus-vector
# retriever later changes this one class.
#
# Pure vector search on purpose: it must reproduce the baseline run report in
# eval/runs (ADR-0030), so any difference is a porting bug, not a changed
# algorithm.

import sys
from pathlib import Path
from typing import Annotated, Any

import psycopg
from langchain_core.callbacks import CallbackManagerForRetrieverRun
from langchain_core.documents import Document
from langchain_core.retrievers import BaseRetriever
from pydantic import SkipValidation

# /store isn't an installable package, so its folder goes on sys.path.
sys.path.insert(0, str(Path(__file__).parent.parent / "store"))

from db import DEFAULT_DB_URL  # noqa: E402  (import must follow the sys.path edit)
from embed import (  # noqa: E402
    EMBEDDING_MODEL,
    EmbeddingClient,
    vector_literal,
)

# The *query* half of nomic-embed-text's asymmetric convention (ADR-0026);
# store/embed.py stored every Chunk with "search_document: ". Omitting it
# still returns results, just quietly worse ones.
QUERY_PREFIX = "search_query: "

# The recorded default for how many Chunks a question retrieves (ADR-0032).
DEFAULT_K = 5

# Same query as eval/run_eval.py's RETRIEVAL_SQL, plus chunks.id and
# chunks.text (a Document needs content, and the Event's retrieve Step needs
# the Chunk id). `<=>` is pgvector's cosine distance; 1 - distance is the
# similarity reported as the score. The join to documents on
# active_chunking_generation_id is what restricts candidates to each
# Document's active Chunking Generation (ADR-0025). chunks.id breaks ties so
# equal distances always come back in the same order.
RETRIEVAL_SQL = """
    SELECT chunks.id,
           chunks.document_id,
           chunks.locator,
           chunks.text,
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


def row_to_document(row: tuple[Any, ...]) -> Document:
    chunk_id, document_id, locator, text, chunking_strategy, similarity = row
    return Document(
        page_content=text,
        metadata={
            "chunk_id": chunk_id,
            "document_id": document_id,
            "locator": locator,
            "score": similarity,
            # Not in the issue's required four: the eval match rule parses a
            # locator according to its Document's strategy (ADR-0028).
            "chunking_strategy": chunking_strategy,
        },
    )


class ChunkRetriever(BaseRetriever):
    db_url: str = DEFAULT_DB_URL
    # Pydantic can't validate a Protocol, so it takes the client as given.
    embedding_client: Annotated[EmbeddingClient, SkipValidation]
    k: int = DEFAULT_K

    def _get_relevant_documents(
        self, query: str, *, run_manager: CallbackManagerForRetrieverRun
    ) -> list[Document]:
        query_vector = self.embedding_client.embed(QUERY_PREFIX + query)
        with psycopg.connect(self.db_url) as conn:
            conn.read_only = True
            with conn.cursor() as cur:
                cur.execute(
                    RETRIEVAL_SQL,
                    {
                        "query": vector_literal(query_vector),
                        "model": EMBEDDING_MODEL,
                        "k": self.k,
                    },
                )
                rows = cur.fetchall()
        documents = []
        for row in rows:
            documents.append(row_to_document(row))
        return documents
