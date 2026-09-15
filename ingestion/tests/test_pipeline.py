# End-to-end tests for pipeline.py: manifest -> extract -> clean -> chunk ->
# validate -> write, run against real corpus PDFs -- CP54 for
# clause_numbered (issue #5), DP8 for heading_sections (issue #6). These
# are the only tests in this ticket exercising every module together rather
# than in isolation; everything else here (test_ids.py, test_clean.py,
# test_clause_numbered.py, test_heading_sections.py, test_extract.py) is a
# focused unit test for one module, following the same shape as
# schema/tests.
#
# The corpus isn't committed to git (see corpus/SOURCES.md -- it's
# re-downloadable, not checked in), so these tests skip themselves rather
# than failing outright when a PDF isn't present locally.

import json
from pathlib import Path

import pytest

from pipeline import build_document_and_chunks, load_manifest, run_pipeline
from validate import load_schema, validate_against_schema

CORPUS_DIR = Path(__file__).parent.parent.parent / "corpus"
CP54_PDF = CORPUS_DIR / "04-cp54-second-consultation-consumer-protection-code.pdf"
DP8_PDF = CORPUS_DIR / "12-dp8-outsourcing-findings-and-issues.pdf"
MANIFEST_PATH = Path(__file__).parent.parent / "manifest.json"

# pytest.mark.skipif decorates every test below with a condition: if it's
# True, pytest reports the test as "skipped" (not failed, not passed)
# rather than running it. The equivalent in nUnit would be
# [Ignore("reason")] applied conditionally rather than unconditionally.
requires_cp54 = pytest.mark.skipif(
    not CP54_PDF.exists(),
    reason="corpus PDFs aren't committed to git -- see corpus/SOURCES.md to download them",
)
requires_dp8 = pytest.mark.skipif(
    not DP8_PDF.exists(),
    reason="corpus PDFs aren't committed to git -- see corpus/SOURCES.md to download them",
)
requires_corpus = pytest.mark.skipif(
    not (CP54_PDF.exists() and DP8_PDF.exists()),
    reason="corpus PDFs aren't committed to git -- see corpus/SOURCES.md to download them",
)


def _entry_for(entries: list[dict], filename: str) -> dict:
    return next(e for e in entries if e["filename"] == filename)


def test_load_manifest_reads_both_entries():
    entries = load_manifest(MANIFEST_PATH)

    assert len(entries) == 2

    cp54 = _entry_for(entries, "04-cp54-second-consultation-consumer-protection-code.pdf")
    assert cp54["chunking_strategy"] == "clause_numbered"

    dp8 = _entry_for(entries, "12-dp8-outsourcing-findings-and-issues.pdf")
    assert dp8["chunking_strategy"] == "heading_sections"


CP54_FILENAME = "04-cp54-second-consultation-consumer-protection-code.pdf"
DP8_FILENAME = "12-dp8-outsourcing-findings-and-issues.pdf"


@requires_cp54
def test_build_document_and_chunks_produces_a_schema_valid_document():
    entries = load_manifest(MANIFEST_PATH)
    document, chunks = build_document_and_chunks(_entry_for(entries, CP54_FILENAME), CORPUS_DIR)

    document_schema = load_schema("document.schema.json")
    validate_against_schema(document, document_schema)


@requires_cp54
def test_build_document_and_chunks_produces_schema_valid_chunks():
    entries = load_manifest(MANIFEST_PATH)
    document, chunks = build_document_and_chunks(_entry_for(entries, CP54_FILENAME), CORPUS_DIR)

    chunk_schema = load_schema("chunk.schema.json")
    assert len(chunks) > 0
    for one_chunk in chunks:
        validate_against_schema(one_chunk, chunk_schema)


@requires_cp54
def test_document_id_is_derived_and_generation_is_active():
    entries = load_manifest(MANIFEST_PATH)
    document, chunks = build_document_and_chunks(_entry_for(entries, CP54_FILENAME), CORPUS_DIR)

    assert document["id"] == "doc-04-cp54-second-consultation-consumer-protection-code"
    # Every chunk belongs to the generation the Document points at as active
    # (ADR-0004) -- proving the pointer was actually wired up, not just
    # present with some other value.
    for one_chunk in chunks:
        assert one_chunk["chunking_generation_id"] == document["active_chunking_generation_id"]
        assert one_chunk["document_id"] == document["id"]


@requires_cp54
def test_chunk_locators_are_bare_clause_numbers_not_page_decorated():
    entries = load_manifest(MANIFEST_PATH)
    document, chunks = build_document_and_chunks(_entry_for(entries, CP54_FILENAME), CORPUS_DIR)

    # A bare clause number like "1.8" -- not "1.8 (p. 7)". heading_sections/
    # academic_sections documents get page-decorated locators (ADR-0015);
    # clause_numbered ones deliberately don't (Q5 of the grilling session).
    #
    # "c for c in chunks if ..." is a *generator expression* -- like the
    # list comprehensions used elsewhere in this project, but without the
    # surrounding [ ], so it produces values lazily one at a time instead of
    # building the whole list up front. next(...) pulls just the first
    # value out of it (and would raise StopIteration if nothing matched) --
    # roughly the same job as C#'s chunks.First(c => c.Locator == "1.8"),
    # but built from two separate, more general pieces (a generator, plus
    # next()) rather than one LINQ method.
    known_real_clause = next(c for c in chunks if c["locator"] == "1.8")
    assert "(p." not in known_real_clause["locator"]


@requires_cp54
def test_repeated_header_is_stripped_from_every_chunk():
    entries = load_manifest(MANIFEST_PATH)
    document, chunks = build_document_and_chunks(_entry_for(entries, CP54_FILENAME), CORPUS_DIR)

    # "Consultation Paper CP 54" is part of the running header repeated on
    # every page -- if header stripping (ADR-0016) is working, it should
    # never survive into any chunk's text.
    for one_chunk in chunks:
        assert "Consultation Paper CP 54" not in one_chunk["text"]


# ---- heading_sections: DP8 (issue #6) ----

@requires_dp8
def test_dp8_build_document_and_chunks_produces_schema_valid_output():
    entries = load_manifest(MANIFEST_PATH)
    document, chunks = build_document_and_chunks(_entry_for(entries, DP8_FILENAME), CORPUS_DIR)

    validate_against_schema(document, load_schema("document.schema.json"))
    chunk_schema = load_schema("chunk.schema.json")
    assert len(chunks) > 0
    for one_chunk in chunks:
        validate_against_schema(one_chunk, chunk_schema)


@requires_dp8
def test_dp8_document_id_is_derived_and_generation_is_active():
    entries = load_manifest(MANIFEST_PATH)
    document, chunks = build_document_and_chunks(_entry_for(entries, DP8_FILENAME), CORPUS_DIR)

    assert document["id"] == "doc-12-dp8-outsourcing-findings-and-issues"
    for one_chunk in chunks:
        assert one_chunk["chunking_generation_id"] == document["active_chunking_generation_id"]
        assert one_chunk["document_id"] == document["id"]


@requires_dp8
def test_dp8_chunk_locators_pair_a_real_heading_with_a_page_number():
    entries = load_manifest(MANIFEST_PATH)
    document, chunks = build_document_and_chunks(_entry_for(entries, DP8_FILENAME), CORPUS_DIR)

    # "Purpose" is a real heading confirmed by direct inspection of the PDF
    # (page 5 of the extracted text) -- proving the strategy found a real
    # bold heading, not just any line, and decorated it with a page number
    # (ADR-0015), unlike clause_numbered's bare locators.
    purpose_chunk = next(c for c in chunks if c["locator"].startswith("Purpose"))
    assert purpose_chunk["locator"] == "Purpose (p. 5)"


@requires_dp8
def test_dp8_repeated_header_and_page_footer_are_stripped_from_every_chunk():
    entries = load_manifest(MANIFEST_PATH)
    document, chunks = build_document_and_chunks(_entry_for(entries, DP8_FILENAME), CORPUS_DIR)

    # Note: checking whole *lines*, not substrings -- "Central Bank of
    # Ireland" and "Outsourcing" are also, unsurprisingly, words that show
    # up constantly within real body prose in a Central Bank paper about
    # outsourcing (e.g. citing "Central Bank of Ireland AIF Rulebook" in a
    # references section). What must never survive is either phrase
    # appearing as its *own standalone line* -- that shape is specific to
    # the running header, not to a sentence that happens to contain the
    # same words.
    for one_chunk in chunks:
        chunk_lines = one_chunk["text"].splitlines()
        assert "Central Bank of Ireland" not in chunk_lines
        assert "Outsourcing" not in chunk_lines
        # DP8's real running footer is "Page <N>" as its own line -- proving
        # the "Page "-prefixed page-number rule (added for this ticket)
        # actually fires on this real document, not just the synthetic test
        # in test_clean.py.
        assert not any(line.startswith("Page ") and line[5:].isdigit() for line in chunk_lines)


@requires_corpus
def test_run_pipeline_writes_validated_output_files_for_every_document(tmp_path):
    output_dir = tmp_path / "output"

    run_pipeline(MANIFEST_PATH, CORPUS_DIR, output_dir)

    document_schema = load_schema("document.schema.json")
    chunk_schema = load_schema("chunk.schema.json")

    for document_id in [
        "doc-04-cp54-second-consultation-consumer-protection-code",
        "doc-12-dp8-outsourcing-findings-and-issues",
    ]:
        document_path = output_dir / "documents" / f"{document_id}.json"
        chunks_path = output_dir / "chunks" / f"{document_id}.json"

        assert document_path.exists()
        assert chunks_path.exists()

        written_document = json.loads(document_path.read_text())
        written_chunks = json.loads(chunks_path.read_text())

        validate_against_schema(written_document, document_schema)
        for one_chunk in written_chunks:
            validate_against_schema(one_chunk, chunk_schema)
