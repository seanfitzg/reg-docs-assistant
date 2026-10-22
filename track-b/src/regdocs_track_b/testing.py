# Fakes shared by the graph tests, so test files don't import each other.
from langchain_core.documents import Document
from langchain_core.retrievers import BaseRetriever


class FakeRetriever(BaseRetriever):
    documents: list[Document]

    def _get_relevant_documents(self, query, *, run_manager):
        return self.documents


def make_chunk(chunk_id, document_id, locator, text, score):
    return Document(
        page_content=text,
        metadata={
            "chunk_id": chunk_id,
            "document_id": document_id,
            "locator": locator,
            "score": score,
        },
    )


CHUNKS = [
    make_chunk("c-1", "doc-a", "3.1", "Firms must give 30 days' notice.", 0.91),
    make_chunk("c-2", "doc-b", "Introduction (p. 2)", "Fees must be disclosed.", 0.74),
]
