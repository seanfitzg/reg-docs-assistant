# End-to-end tests for pipeline.py: manifest -> extract -> clean -> chunk ->
# validate -> write, run against real corpus PDFs -- CP54 for
# clause_numbered (issue #5), DP8 for heading_sections (issue #6), RTP07/19
# for academic_sections (issue #7), DP7 and FSR for manifest-flagged cleanup
# (ADR-0016, issue #9). These are the only tests in this ticket exercising
# every module together rather than in isolation; everything else here
# (test_ids.py, test_clean.py, test_clause_numbered.py,
# test_heading_sections.py, test_academic_sections.py, test_extract.py) is
# a focused unit test for one module, following the same shape as
# schema/tests.
#
# The corpus isn't committed to git (see corpus/SOURCES.md -- it's
# re-downloadable, not checked in), so these tests skip themselves rather
# than failing outright when a PDF isn't present locally.

import json
import unicodedata
from pathlib import Path

import pytest

from pipeline import build_document_and_chunks, load_manifest, run_pipeline
from validate import load_schema, validate_against_schema

CORPUS_DIR = Path(__file__).parent.parent.parent / "corpus"
CP54_PDF = CORPUS_DIR / "04-cp54-second-consultation-consumer-protection-code.pdf"
DP7_PDF = CORPUS_DIR / "11-dp7-digitalisation-and-consumer-protection-code.pdf"
DP8_PDF = CORPUS_DIR / "12-dp8-outsourcing-findings-and-issues.pdf"
RTP_PDF = CORPUS_DIR / "19-rtp-07rt19-money-market-funds-unconventional-policy.pdf"
FSR_PDF = CORPUS_DIR / "17-fsr-2026-i-financial-stability-review.pdf"
MANIFEST_PATH = Path(__file__).parent.parent / "manifest.json"

# pytest.mark.skipif decorates every test below with a condition: if it's
# True, pytest reports the test as "skipped" (not failed, not passed)
# rather than running it. The equivalent in nUnit would be
# [Ignore("reason")] applied conditionally rather than unconditionally.
requires_cp54 = pytest.mark.skipif(
    not CP54_PDF.exists(),
    reason="corpus PDFs aren't committed to git -- see corpus/SOURCES.md to download them",
)
requires_dp7 = pytest.mark.skipif(
    not DP7_PDF.exists(),
    reason="corpus PDFs aren't committed to git -- see corpus/SOURCES.md to download them",
)
requires_dp8 = pytest.mark.skipif(
    not DP8_PDF.exists(),
    reason="corpus PDFs aren't committed to git -- see corpus/SOURCES.md to download them",
)
requires_rtp = pytest.mark.skipif(
    not RTP_PDF.exists(),
    reason="corpus PDFs aren't committed to git -- see corpus/SOURCES.md to download them",
)
requires_fsr = pytest.mark.skipif(
    not FSR_PDF.exists(),
    reason="corpus PDFs aren't committed to git -- see corpus/SOURCES.md to download them",
)
requires_corpus = pytest.mark.skipif(
    not (CP54_PDF.exists() and DP7_PDF.exists() and DP8_PDF.exists() and RTP_PDF.exists() and FSR_PDF.exists()),
    reason="corpus PDFs aren't committed to git -- see corpus/SOURCES.md to download them",
)


def _entry_for(entries: list[dict], filename: str) -> dict:
    return next(e for e in entries if e["filename"] == filename)


def test_load_manifest_reads_all_five_entries():
    entries = load_manifest(MANIFEST_PATH)

    assert len(entries) == 5

    cp54 = _entry_for(entries, "04-cp54-second-consultation-consumer-protection-code.pdf")
    assert cp54["chunking_strategy"] == "clause_numbered"

    dp8 = _entry_for(entries, "12-dp8-outsourcing-findings-and-issues.pdf")
    assert dp8["chunking_strategy"] == "heading_sections"

    rtp = _entry_for(entries, "19-rtp-07rt19-money-market-funds-unconventional-policy.pdf")
    assert rtp["chunking_strategy"] == "academic_sections"

    dp7 = _entry_for(entries, "11-dp7-digitalisation-and-consumer-protection-code.pdf")
    assert dp7["chunking_strategy"] == "heading_sections"
    assert dp7["cleanup_flags"] == [
        {"type": "navigation_chrome", "pattern": "Annex \\d", "minimum_matches": 4}
    ]

    fsr = _entry_for(entries, "17-fsr-2026-i-financial-stability-review.pdf")
    assert fsr["chunking_strategy"] == "heading_sections"
    assert fsr["cleanup_flags"] == [
        {
            "type": "duplicate_section_removal",
            "start_heading": "Réamhrá",
            "end_heading": "Global risk assessment",
        }
    ]


CP54_FILENAME = "04-cp54-second-consultation-consumer-protection-code.pdf"
DP8_FILENAME = "12-dp8-outsourcing-findings-and-issues.pdf"
RTP_FILENAME = "19-rtp-07rt19-money-market-funds-unconventional-policy.pdf"


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


# ---- academic_sections: RTP07/19 (issue #7) ----

@requires_rtp
def test_rtp_build_document_and_chunks_produces_schema_valid_output():
    entries = load_manifest(MANIFEST_PATH)
    document, chunks = build_document_and_chunks(_entry_for(entries, RTP_FILENAME), CORPUS_DIR)

    validate_against_schema(document, load_schema("document.schema.json"))
    chunk_schema = load_schema("chunk.schema.json")
    assert len(chunks) > 0
    for one_chunk in chunks:
        validate_against_schema(one_chunk, chunk_schema)


@requires_rtp
def test_rtp_document_id_is_derived_and_generation_is_active():
    entries = load_manifest(MANIFEST_PATH)
    document, chunks = build_document_and_chunks(_entry_for(entries, RTP_FILENAME), CORPUS_DIR)

    assert document["id"] == "doc-19-rtp-07rt19-money-market-funds-unconventional-policy"
    for one_chunk in chunks:
        assert one_chunk["chunking_generation_id"] == document["active_chunking_generation_id"]
        assert one_chunk["document_id"] == document["id"]


@requires_rtp
def test_rtp_chunk_locators_pair_a_real_heading_with_a_page_number():
    entries = load_manifest(MANIFEST_PATH)
    document, chunks = build_document_and_chunks(_entry_for(entries, RTP_FILENAME), CORPUS_DIR)

    # "Introduction" is a real, single-line heading confirmed by direct
    # inspection of the PDF (page 4) -- proving the strategy found a real
    # bold heading and decorated it with a page number (ADR-0015).
    introduction_chunk = next(c for c in chunks if c["locator"] == "Introduction (p. 4)")
    assert introduction_chunk["text"]


@requires_rtp
def test_rtp_a_heading_wrapped_across_two_bold_lines_is_joined_in_the_real_pdf():
    entries = load_manifest(MANIFEST_PATH)
    document, chunks = build_document_and_chunks(_entry_for(entries, RTP_FILENAME), CORPUS_DIR)

    # Appendix A's heading is genuinely two consecutive bold lines in this
    # PDF ("A Sources and Construction of Variables Used in Panel" /
    # "Regressions") -- confirming academic_sections' join behaviour
    # (module-level docstring) fires correctly against the real document,
    # not just the synthetic fixture in test_academic_sections.py.
    appendix_chunk = next(c for c in chunks if c["locator"].startswith("A Sources"))
    assert appendix_chunk["locator"] == (
        "A Sources and Construction of Variables Used in Panel Regressions (p. 26)"
    )


@requires_rtp
def test_rtp_extracted_text_recovers_ligatured_words_cleanly():
    # pypdf previously corrupted this document's text (garbled
    # glyphs/ligatures -- see extract.py's module comment); pymupdf's fix is
    # what unblocked this ticket (#7 was blocked by #5). pymupdf represents
    # an "fi" pair as a single ligature codepoint (U+FB01) rather than
    # corrupting it, so a plain substring search for "certificates" won't
    # match directly -- unicodedata.normalize("NFKC", ...) is the standard
    # decomposition that turns a compatibility ligature character back into
    # its component letters, the same way "①" normalizes to "1". Doing that
    # here and finding the real word proves the extracted text is genuine,
    # recoverable Unicode -- not corrupted -- confirming the fix holds
    # inside the real pipeline, not just the earlier scratch check.
    entries = load_manifest(MANIFEST_PATH)
    document, chunks = build_document_and_chunks(_entry_for(entries, RTP_FILENAME), CORPUS_DIR)

    abstract_chunk = next(c for c in chunks if c["locator"] == "Abstract (p. 2)")
    normalized_text = unicodedata.normalize("NFKC", abstract_chunk["text"])
    assert "certificates of deposits" in normalized_text


# ---- manifest-flagged cleanup: DP7 "navigation_chrome" (ADR-0016, issue #9,
# ---- parameterised in issue #13) ----

DP7_FILENAME = "11-dp7-digitalisation-and-consumer-protection-code.pdf"
FSR_FILENAME = "17-fsr-2026-i-financial-stability-review.pdf"


@requires_dp7
def test_dp7_build_document_and_chunks_produces_schema_valid_output():
    entries = load_manifest(MANIFEST_PATH)
    document, chunks = build_document_and_chunks(_entry_for(entries, DP7_FILENAME), CORPUS_DIR)

    validate_against_schema(document, load_schema("document.schema.json"))
    chunk_schema = load_schema("chunk.schema.json")
    assert len(chunks) > 0
    for one_chunk in chunks:
        validate_against_schema(one_chunk, chunk_schema)


@requires_dp7
def test_dp7_navigation_chrome_footer_is_stripped_from_every_chunk():
    entries = load_manifest(MANIFEST_PATH)
    document, chunks = build_document_and_chunks(_entry_for(entries, DP7_FILENAME), CORPUS_DIR)

    # The real DP7 PDF's Annex pages carry a nav-breadcrumb footer like
    # "Annex 1 page 1 of 3 >  | Annex 2  | Annex 3  | Annex 4" -- confirmed
    # by direct inspection of the extracted text. If the navigation_chrome
    # flag (declared on this document's manifest entry) is working, no
    # chunk should ever contain the "page X of Y" fragment that's specific
    # to that footer, on any Annex.
    for one_chunk in chunks:
        for total in (2, 3):
            for page_number in range(1, total + 1):
                assert f"page {page_number} of {total}" not in one_chunk["text"]


@requires_dp7
def test_dp7_a_real_annex_toc_entry_survives_the_navigation_chrome_flag():
    # The navigation_chrome flag must be specific to the nav footer, not so
    # broad it deletes legitimate content that happens to mention an Annex
    # -- DP7's own Table of Contents lists "Annex 2" as one of its entries,
    # confirmed by direct inspection of the real PDF.
    entries = load_manifest(MANIFEST_PATH)
    document, chunks = build_document_and_chunks(_entry_for(entries, DP7_FILENAME), CORPUS_DIR)

    assert any("Annex 2" in one_chunk["text"] for one_chunk in chunks)


# ---- manifest-flagged cleanup: FSR "duplicate_section_removal" (ADR-0016,
# ---- issue #9, parameterised in issue #13) ----

@requires_fsr
def test_fsr_build_document_and_chunks_produces_schema_valid_output():
    entries = load_manifest(MANIFEST_PATH)
    document, chunks = build_document_and_chunks(_entry_for(entries, FSR_FILENAME), CORPUS_DIR)

    validate_against_schema(document, load_schema("document.schema.json"))
    chunk_schema = load_schema("chunk.schema.json")
    assert len(chunks) > 0
    for one_chunk in chunks:
        validate_against_schema(one_chunk, chunk_schema)


@requires_fsr
def test_fsr_irish_duplicate_sections_produce_no_chunks_of_their_own():
    entries = load_manifest(MANIFEST_PATH)
    document, chunks = build_document_and_chunks(_entry_for(entries, FSR_FILENAME), CORPUS_DIR)

    # "Réamhrá"/"Forbhreathnú" (Irish for "Preface"/"Overview") are the real
    # section headings the Irish duplicate content sits under in the source
    # PDF -- confirmed by direct inspection. If the duplicate_section_removal
    # flag is working (this document's manifest entry sets its start_heading
    # to "Réamhrá"), neither should survive as a locator of its own.
    locators = [one_chunk["locator"] for one_chunk in chunks]
    assert not any(locator.startswith("Réamhrá") for locator in locators)
    assert not any(locator.startswith("Forbhreathnú") for locator in locators)


@requires_fsr
def test_fsr_english_content_either_side_of_the_irish_section_survives():
    # The flag must remove only the Irish duplicate span, not the real
    # English content immediately before it ("Preface") or after it
    # ("Global risk assessment") -- both real headings confirmed by direct
    # inspection of the real PDF.
    entries = load_manifest(MANIFEST_PATH)
    document, chunks = build_document_and_chunks(_entry_for(entries, FSR_FILENAME), CORPUS_DIR)

    locators = [one_chunk["locator"] for one_chunk in chunks]
    assert any(locator.startswith("Preface") for locator in locators)
    assert any(locator.startswith("Global risk assessment") for locator in locators)


@requires_corpus
def test_run_pipeline_writes_validated_output_files_for_every_document(tmp_path):
    output_dir = tmp_path / "output"

    run_pipeline(MANIFEST_PATH, CORPUS_DIR, output_dir)

    document_schema = load_schema("document.schema.json")
    chunk_schema = load_schema("chunk.schema.json")

    for document_id in [
        "doc-04-cp54-second-consultation-consumer-protection-code",
        "doc-12-dp8-outsourcing-findings-and-issues",
        "doc-19-rtp-07rt19-money-market-funds-unconventional-policy",
        "doc-11-dp7-digitalisation-and-consumer-protection-code",
        "doc-17-fsr-2026-i-financial-stability-review",
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
