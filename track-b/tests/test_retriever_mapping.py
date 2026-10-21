# Fast unit tests for how a database row becomes a LangChain Document. No
# Postgres, no Ollama.

from retriever import DEFAULT_K, ChunkRetriever, row_to_document


class UnusedClient:
    def embed(self, text: str) -> list[float]:
        raise AssertionError("not expected to embed")


def test_row_becomes_document_with_chunk_text_and_metadata():
    row = ("c-1.1", "doc-a", "1.1", "Firms must act.", "clause_numbered", 0.83)

    document = row_to_document(row)

    assert document.page_content == "Firms must act."
    assert document.metadata == {
        "chunk_id": "c-1.1",
        "document_id": "doc-a",
        "locator": "1.1",
        "score": 0.83,
        "chunking_strategy": "clause_numbered",
    }


def test_k_defaults_to_five():
    retriever = ChunkRetriever(embedding_client=UnusedClient())

    assert DEFAULT_K == 5
    assert retriever.k == 5


def test_k_is_configurable():
    retriever = ChunkRetriever(embedding_client=UnusedClient(), k=10)

    assert retriever.k == 10
