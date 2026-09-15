# End-to-end test for pipeline.py: manifest -> extract -> clean -> chunk ->
# validate -> write, run against the real CP54 PDF (issue #5's acceptance
# criteria). This is the one test in this ticket that exercises every
# module together rather than in isolation -- everything else here
# (test_ids.py, test_clean.py, test_clause_numbered.py, test_extract.py)
# is a focused unit test for one module, following the same shape as
# schema/tests.
#
# The corpus isn't committed to git (see corpus/SOURCES.md -- it's
# re-downloadable, not checked in), so this test skips itself rather than
# failing outright when the PDF isn't present locally.

import json
from pathlib import Path

import jsonschema
import pytest

from pipeline import build_document_and_chunks, load_manifest, run_pipeline
from validate import load_schema, validate_against_schema

CORPUS_DIR = Path(__file__).parent.parent.parent / "corpus"
CP54_PDF = CORPUS_DIR / "04-cp54-second-consultation-consumer-protection-code.pdf"
MANIFEST_PATH = Path(__file__).parent.parent / "manifest.json"

# pytest.mark.skipif decorates every test below with a condition: if it's
# True, pytest reports the test as "skipped" (not failed, not passed)
# rather than running it. The equivalent in nUnit would be
# [Ignore("reason")] applied conditionally rather than unconditionally.
requires_corpus = pytest.mark.skipif(
    not CP54_PDF.exists(),
    reason="corpus PDFs aren't committed to git -- see corpus/SOURCES.md to download them",
)


def test_load_manifest_reads_the_cp54_entry():
    entries = load_manifest(MANIFEST_PATH)

    assert len(entries) == 1
    assert entries[0]["filename"] == "04-cp54-second-consultation-consumer-protection-code.pdf"
    assert entries[0]["chunking_strategy"] == "clause_numbered"


@requires_corpus
def test_build_document_and_chunks_produces_a_schema_valid_document():
    entries = load_manifest(MANIFEST_PATH)
    document, chunks = build_document_and_chunks(entries[0], CORPUS_DIR)

    document_schema = load_schema("document.schema.json")
    validate_against_schema(document, document_schema)


@requires_corpus
def test_build_document_and_chunks_produces_schema_valid_chunks():
    entries = load_manifest(MANIFEST_PATH)
    document, chunks = build_document_and_chunks(entries[0], CORPUS_DIR)

    chunk_schema = load_schema("chunk.schema.json")
    assert len(chunks) > 0
    for one_chunk in chunks:
        validate_against_schema(one_chunk, chunk_schema)


@requires_corpus
def test_document_id_is_derived_and_generation_is_active():
    entries = load_manifest(MANIFEST_PATH)
    document, chunks = build_document_and_chunks(entries[0], CORPUS_DIR)

    assert document["id"] == "doc-04-cp54-second-consultation-consumer-protection-code"
    # Every chunk belongs to the generation the Document points at as active
    # (ADR-0004) -- proving the pointer was actually wired up, not just
    # present with some other value.
    for one_chunk in chunks:
        assert one_chunk["chunking_generation_id"] == document["active_chunking_generation_id"]
        assert one_chunk["document_id"] == document["id"]


@requires_corpus
def test_chunk_locators_are_bare_clause_numbers_not_page_decorated():
    entries = load_manifest(MANIFEST_PATH)
    document, chunks = build_document_and_chunks(entries[0], CORPUS_DIR)

    # A bare clause number like "1.8" -- not "1.8 (p. 7)". heading_sections/
    # academic_sections documents get page-decorated locators (ADR-0015);
    # clause_numbered ones deliberately don't (Q5 of the grilling session).
    known_real_clause = next(c for c in chunks if c["locator"] == "1.8")
    assert "(p." not in known_real_clause["locator"]


@requires_corpus
def test_repeated_header_is_stripped_from_every_chunk():
    entries = load_manifest(MANIFEST_PATH)
    document, chunks = build_document_and_chunks(entries[0], CORPUS_DIR)

    # "Consultation Paper CP 54" is part of the running header repeated on
    # every page -- if header stripping (ADR-0016) is working, it should
    # never survive into any chunk's text.
    for one_chunk in chunks:
        assert "Consultation Paper CP 54" not in one_chunk["text"]


@requires_corpus
def test_run_pipeline_writes_validated_output_files(tmp_path):
    output_dir = tmp_path / "output"

    run_pipeline(MANIFEST_PATH, CORPUS_DIR, output_dir)

    document_path = output_dir / "documents" / "doc-04-cp54-second-consultation-consumer-protection-code.json"
    chunks_path = output_dir / "chunks" / "doc-04-cp54-second-consultation-consumer-protection-code.json"

    assert document_path.exists()
    assert chunks_path.exists()

    written_document = json.loads(document_path.read_text())
    written_chunks = json.loads(chunks_path.read_text())

    validate_against_schema(written_document, load_schema("document.schema.json"))
    chunk_schema = load_schema("chunk.schema.json")
    for one_chunk in written_chunks:
        validate_against_schema(one_chunk, chunk_schema)
