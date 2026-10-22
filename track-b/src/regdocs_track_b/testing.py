# Fakes shared by the graph tests, so test files don't import each other.
from langchain_core.documents import Document
from langchain_core.language_models.fake_chat_models import FakeListChatModel
from langchain_core.retrievers import BaseRetriever


class FakeRetriever(BaseRetriever):
    documents: list[Document]

    def _get_relevant_documents(self, query, *, run_manager):
        return self.documents


class RecordingModel(FakeListChatModel):
    prompts: list[str]

    def _call(self, messages, stop=None, run_manager=None, **kwargs):
        self.prompts.append(messages[-1].content)
        return super()._call(messages, stop, run_manager, **kwargs)


def safe_classifier():
    return FakeListChatModel(responses=["NO"])


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
