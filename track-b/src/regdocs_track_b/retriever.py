# Track B's retriever (ADR-0032): a LangChain retriever over the existing
# chunk_embeddings table, not LangChain's own PGVector integration.
#
# Downstream code sees only LangChain's retriever interface, so a later hybrid
# retriever changes this one class.
#
# Pure vector search on purpose: it must reproduce the baseline run report in
# eval/runs (ADR-0030), so any difference is a porting bug, not a changed
# algorithm.

from typing import Annotated, Any

import psycopg
from langchain_core.callbacks import CallbackManagerForRetrieverRun
from langchain_core.documents import Document
from langchain_core.retrievers import BaseRetriever
from pydantic import SkipValidation
from regdocs_store.db import DEFAULT_DB_URL
from regdocs_store.embed import (
    EMBEDDING_MODEL,
    EmbeddingClient,
    vector_literal,
)

# Query half of nomic-embed-text's asymmetric prefixes (ADR-0026).
QUERY_PREFIX = "search_query: "

# The recorded default for how many Chunks a question retrieves (ADR-0032).
DEFAULT_K = 5

# Same query as regdocs_eval.run_eval's RETRIEVAL_SQL, plus chunks.id and
# chunks.text (a Document needs content, and the Event's retrieve Step needs
# the Chunk id). The join to documents on active_chunking_generation_id
# restricts candidates to active Chunking Generations (ADR-0025); chunks.id
# breaks ties so equal distances keep a stable order.
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
