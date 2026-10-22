# Graph-seam tests for the real draft and its numbered Citations (issue #42,
# ADR-0010): a scripted fake chat model answers with [n] markers and the graph
# resolves them by lookup against the retrieved Chunks.

import pytest
from langchain_core.language_models.fake_chat_models import FakeListChatModel

from regdocs_track_b.graph import build_graph
from regdocs_track_b.testing import CHUNKS, FakeRetriever, RecordingModel


def _invoke(answer):
    graph = build_graph(
        retriever=FakeRetriever(documents=CHUNKS),
        chat_model=FakeListChatModel(responses=[answer]),
        draft_model_name="fake-chat",
    )
    return graph.invoke({"question": "How much notice?", "steps": []})


def _markers(final):
    markers = []
    for citation in final["citations"]:
        markers.append(citation["marker"])
    return markers


def test_markers_resolve_to_the_document_and_locator_of_the_numbered_chunk():
    final = _invoke("Give 30 days' notice [1] and disclose fees [2].")

    assert final["answer"] == "Give 30 days' notice [1] and disclose fees [2]."
    assert final["citations"] == [
        {
            "marker": 1,
            "chunk_id": "c-1",
            "document_id": "doc-a",
            "locator": "3.1",
        },
        {
            "marker": 2,
            "chunk_id": "c-2",
            "document_id": "doc-b",
            "locator": "Introduction (p. 2)",
        },
    ]


def test_out_of_range_markers_are_not_cited_and_are_stripped_from_the_answer():
    final = _invoke("Give 30 days' notice [1], see also [0] and [9] and [3].")

    assert final["answer"] == "Give 30 days' notice [1], see also and and."
    assert _markers(final) == [1]


def test_a_marker_cited_twice_yields_one_citation():
    final = _invoke("Notice is 30 days [1]. Again, 30 days [1].")

    assert _markers(final) == [1]


def test_prompt_comes_from_a_file_and_numbers_chunks_in_rank_order(tmp_path):
    prompt_file = tmp_path / "draft-test.txt"
    prompt_file.write_text("RULES v-test\n{context}\nQ: {question}", encoding="utf-8")
    model = RecordingModel(responses=["ok [1]"], prompts=[])
    graph = build_graph(
        retriever=FakeRetriever(documents=CHUNKS),
        chat_model=model,
        draft_model_name="fake-chat",
        draft_prompt_path=prompt_file,
    )

    graph.invoke({"question": "How much notice?", "steps": []})

    assert model.prompts == [
        "RULES v-test\n"
        "[1] Firms must give 30 days' notice.\n\n"
        "[2] Fees must be disclosed.\n"
        "Q: How much notice?"
    ]


def test_a_missing_prompt_file_fails_when_the_graph_is_built(tmp_path):
    with pytest.raises(FileNotFoundError):
        build_graph(
            retriever=FakeRetriever(documents=CHUNKS),
            chat_model=FakeListChatModel(responses=["x"]),
            draft_model_name="fake-chat",
            draft_prompt_path=tmp_path / "absent.txt",
        )


def test_an_answer_that_is_only_a_bad_marker_fails_loudly():
    with pytest.raises(ValueError, match="draft"):
        _invoke("[9]")


def test_stripping_a_bad_marker_keeps_paragraph_breaks():
    final = _invoke("First point [1].\n\n[9] Second point.")

    assert final["answer"] == "First point [1].\n\nSecond point."
