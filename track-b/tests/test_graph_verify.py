# Graph-seam tests for the real verify Step (issue #47, ADR-0006): a scripted
# fake judge returns per-claim verdicts, code computes Confidence and raises the
# Flags, and nothing is ever retried. Offline.

from pathlib import Path

from langchain_core.language_models.fake_chat_models import FakeListChatModel
from ollama import ResponseError

from regdocs_schema.testing import load_json, validate
from regdocs_track_b.graph import answer_question, build_graph
from regdocs_track_b.testing import (
    CHUNKS,
    FakeRetriever,
    RecordingModel,
    safe_classifier,
)

EVENT_SCHEMA = load_json(
    Path(__file__).parent.parent.parent / "schema" / "event.schema.json"
)

ALL_SUPPORTED = "SUPPORTED: Firms must give 30 days' notice. [1]"
HALF_SUPPORTED = "SUPPORTED: Notice is 30 days.\nUNSUPPORTED: Fees are capped at 2%."
NONE_SUPPORTED = "UNSUPPORTED: Fees are capped at 2%.\nUNSUPPORTED: Notice is 5 days."


def _event(judge_reply, draft_model=None, judge=None):
    graph = build_graph(
        retriever=FakeRetriever(documents=CHUNKS),
        chat_model=draft_model or FakeListChatModel(responses=["Thirty days. [1]"]),
        draft_model_name="fake-chat",
        classifier_model=safe_classifier(),
        classifier_model_name="fake-classifier",
        judge_model=judge or FakeListChatModel(responses=[judge_reply]),
        judge_model_name="fake-judge",
    )
    return answer_question(graph, "How much notice must a firm give?")


def _verify_step(event):
    return event["steps"][3]


def test_confidence_is_computed_in_code_from_the_per_claim_verdicts():
    event = _event(HALF_SUPPORTED)

    assert _verify_step(event)["confidence"] == 0.5
    validate(event, EVENT_SCHEMA)


def test_the_verify_step_records_the_judge_model_not_stub():
    event = _event(ALL_SUPPORTED)

    assert _verify_step(event)["model"] == "fake-judge"


def test_a_fully_supported_answer_raises_no_flags():
    event = _event(ALL_SUPPORTED)

    assert _verify_step(event)["confidence"] == 1.0
    assert event["flags"] == []


def test_partial_support_raises_low_confidence_only_and_keeps_the_answer():
    event = _event(HALF_SUPPORTED)

    assert event["flags"] == ["low_confidence"]
    assert event["answer"] == "Thirty days. [1]"


def test_no_supported_claim_raises_both_flags():
    event = _event(NONE_SUPPORTED)

    assert _verify_step(event)["confidence"] == 0.0
    assert event["flags"] == ["low_confidence", "no_supporting_context"]


def test_an_unreadable_judge_reply_counts_as_unverified():
    event = _event("Looks fine to me!")

    assert _verify_step(event)["confidence"] == 0.0
    assert event["flags"] == ["low_confidence", "no_supporting_context"]
    validate(event, EVENT_SCHEMA)


def test_the_judge_sees_the_answer_and_the_numbered_excerpts(tmp_path):
    prompt_file = tmp_path / "verify-test.txt"
    prompt_file.write_text("JUDGE v-test\n{context}\nA: {answer}", encoding="utf-8")
    judge = RecordingModel(responses=[ALL_SUPPORTED], prompts=[])
    graph = build_graph(
        retriever=FakeRetriever(documents=CHUNKS),
        chat_model=FakeListChatModel(responses=["Thirty days. [1]"]),
        draft_model_name="fake-chat",
        classifier_model=safe_classifier(),
        classifier_model_name="fake-classifier",
        judge_model=judge,
        judge_model_name="fake-judge",
        verify_prompt_path=prompt_file,
    )

    answer_question(graph, "How much notice?")

    assert judge.prompts == [
        "JUDGE v-test\n"
        "[1] Firms must give 30 days' notice.\n\n"
        "[2] Fees must be disclosed.\n"
        "A: Thirty days. [1]"
    ]


def test_verify_never_retries_or_re_drafts():
    draft_model = RecordingModel(responses=["Thirty days. [1]"], prompts=[])
    judge = RecordingModel(responses=[NONE_SUPPORTED], prompts=[])

    event = _event(None, draft_model=draft_model, judge=judge)

    assert len(draft_model.prompts) == 1
    assert len(judge.prompts) == 1
    step_types = []
    for step in event["steps"]:
        step_types.append(step["step_type"])
    assert step_types == ["classify", "retrieve", "draft", "verify"]


class _AbortingJudge(FakeListChatModel):
    def _call(self, messages, stop=None, run_manager=None, **kwargs):
        raise ResponseError("prediction aborted, token repeat limit reached")


def test_a_judge_aborted_by_ollama_leaves_the_answer_unverified_not_a_500():
    event = _event(None, judge=_AbortingJudge(responses=[]))

    assert event["answer"] == "Thirty days. [1]"
    assert _verify_step(event)["confidence"] == 0.0
    assert event["flags"] == ["low_confidence", "no_supporting_context"]
