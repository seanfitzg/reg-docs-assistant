# End-to-end tests for pipeline.py: manifest -> extract -> clean -> chunk ->
# validate -> write, run against real corpus PDFs -- CP54 for
# clause_numbered (issue #5), DP8 for heading_sections (issue #6), RTP07/19
# for academic_sections (issue #7), DP7 and FSR for manifest-flagged cleanup
# (ADR-0016, issue #9), and the full 20-document corpus (issue #10). These
# are the only tests in this ticket exercising every module together rather
# than in isolation; everything else here (test_ids.py, test_clean.py,
# test_clause_numbered.py, test_heading_sections.py, test_academic_sections.py,
# test_extract.py) is a focused unit test for one module, following the same
# shape as schema/tests.
#
# The corpus isn't committed to git (see corpus/SOURCES.md -- it's
# re-downloadable, not checked in), so these tests skip themselves rather
# than failing outright when a PDF isn't present locally.

import json
import logging
import unicodedata
from pathlib import Path

import pytest

from ids import document_id_from_filename
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
# The issue #10 tests below need every PDF the manifest actually declares,
# not just the five other tests in this file individually depend on -- a
# separate guard so those specific tests skip (rather than fail) on a
# machine that only has a partial corpus downloaded. Checking each declared
# filename's existence (not just counting *.pdf files in the directory)
# means this stays correct even if the corpus directory ever has stray
# extra PDFs sitting in it that aren't in the manifest.
requires_full_corpus = pytest.mark.skipif(
    not all((CORPUS_DIR / entry["filename"]).exists() for entry in load_manifest(MANIFEST_PATH)),
    reason="corpus PDFs aren't committed to git -- see corpus/SOURCES.md to download them",
)


def _entry_for(entries: list[dict], filename: str) -> dict:
    return next(e for e in entries if e["filename"] == filename)


def test_load_manifest_reads_all_twenty_entries():
    entries = load_manifest(MANIFEST_PATH)

    assert len(entries) == 20

    cp54 = _entry_for(entries, "04-cp54-second-consultation-consumer-protection-code.pdf")
    assert cp54["chunking_strategy"] == "clause_numbered"
    # CP54 is the Central Bank's second consultation on the same Code review
    # CP47 opened -- its manifest entry should link back to CP47 (ADR-0002),
    # confirmed by direct inspection of both documents' cover text (issue #10).
    assert cp54["supersedes"] == "doc-03-cp47-review-of-consumer-protection-code"

    cp158 = _entry_for(entries, "09-cp158-consumer-protection-code.pdf")
    # heading_sections, not clause_numbered -- confirmed by direct inspection
    # (issue #10): unlike CP54/CP131, CP158's body prose isn't consistently
    # decimal-clause-numbered throughout. clause_numbered on this document
    # produces duplicate locators (a "2.1"-"3.5" run from the Table of
    # Contents' dotted page-reference lines, then a second, real "2.1"-"3.5"
    # run for the body) and one 43,762-character mega-chunk covering
    # everything the sparse real clause markers miss -- heading_sections
    # instead finds 98 clean, bounded chunks (each under ~7KB) using this
    # document's real titled sections ("Chapter 1: Introduction", "A
    # Modernised Code", ...).
    assert cp158["chunking_strategy"] == "heading_sections"
    # CP158's own text cites "Our 2022 Code Review Discussion Paper" as its
    # direct predecessor -- not DP7 (a narrower, single-topic 2017 paper on
    # digitalisation specifically, never mentioned anywhere in CP158). That
    # 2022 discussion paper isn't one of this corpus's 20 documents, so
    # there's no real Document id CP158 could correctly supersede -- setting
    # one anyway (even to the "nearest" discussion paper in the corpus)
    # would record a factually wrong link, which is worse than recording
    # none (ADR-0010's same "wrong but plausible beats obviously missing"
    # reasoning, applied here to Supersedes rather than a citation).
    assert cp158["supersedes"] is None

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


# ---- full 20-document corpus (issue #10) ----
#
# Everything above already exercises one representative document per
# chunking strategy/cleanup flag; these tests instead check the corpus as a
# *whole* -- every real document actually makes it through the pipeline
# (the acceptance criteria's "no document silently fails or is skipped
# without a surfaced reason"), and the two supersedes links resolve
# correctly end to end.

@requires_full_corpus
def test_run_pipeline_writes_validated_output_files_for_every_document(tmp_path):
    output_dir = tmp_path / "output"

    manifest_entries = load_manifest(MANIFEST_PATH)
    results = run_pipeline(MANIFEST_PATH, CORPUS_DIR, output_dir)

    # run_pipeline returns one (document, chunks) pair per entry it
    # successfully ingested (ADR-0019) -- its length matching the
    # manifest's own entry count is the strongest available proof every one
    # of the 20 real corpus documents actually made it through, not just
    # that *some* number of documents did.
    assert len(results) == len(manifest_entries) == 20

    document_schema = load_schema("document.schema.json")
    chunk_schema = load_schema("chunk.schema.json")

    for entry in manifest_entries:
        document_id = document_id_from_filename(entry["filename"])
        document_path = output_dir / "documents" / f"{document_id}.json"
        chunks_path = output_dir / "chunks" / f"{document_id}.json"

        assert document_path.exists()
        assert chunks_path.exists()

        written_document = json.loads(document_path.read_text(encoding="utf-8"))
        written_chunks = json.loads(chunks_path.read_text(encoding="utf-8"))

        validate_against_schema(written_document, document_schema)
        assert len(written_chunks) > 0
        for one_chunk in written_chunks:
            validate_against_schema(one_chunk, chunk_schema)


@requires_full_corpus
def test_run_pipeline_surfaces_no_silent_failures_across_the_full_corpus(tmp_path, caplog):
    # ADR-0019/issue #8's per-document failure isolation exists precisely so
    # one bad document can't take down the batch -- but issue #10's own
    # acceptance criterion runs the other direction: against the *real*
    # 20-document corpus, nothing should actually trigger that isolation.
    # run_pipeline only ever logs at ERROR level when it skips an entry
    # (pipeline.py's except block), so asserting no ERROR records were
    # emitted during a full real run is a direct check against "no document
    # silently fails" -- caplog is pytest's built-in fixture for asserting
    # on logging output, the same idea as asserting on a captured
    # ILogger<T> in a .NET test.
    output_dir = tmp_path / "output"
    with caplog.at_level(logging.ERROR):
        run_pipeline(MANIFEST_PATH, CORPUS_DIR, output_dir)

    assert caplog.records == []


@requires_full_corpus
def test_run_pipeline_writes_the_supersedes_link_for_cp54(tmp_path):
    output_dir = tmp_path / "output"

    run_pipeline(MANIFEST_PATH, CORPUS_DIR, output_dir)

    cp54_path = output_dir / "documents" / "doc-04-cp54-second-consultation-consumer-protection-code.json"
    cp54_document = json.loads(cp54_path.read_text(encoding="utf-8"))
    assert cp54_document["supersedes"] == "doc-03-cp47-review-of-consumer-protection-code"


@requires_full_corpus
def test_run_pipeline_writes_no_supersedes_key_for_cp158(tmp_path):
    # CP158's manifest entry deliberately has no supersedes link (see
    # test_load_manifest_reads_all_twenty_entries for why) -- pipeline.py's
    # build_document_and_chunks only adds the "supersedes" key to a Document
    # when entry.get("supersedes") is truthy, so the written JSON should
    # never contain the key at all, not the key set to null (document.schema
    # .json's "supersedes" field isn't in "required", and null wouldn't pass
    # its "type": "string" validation anyway).
    output_dir = tmp_path / "output"

    run_pipeline(MANIFEST_PATH, CORPUS_DIR, output_dir)

    cp158_path = output_dir / "documents" / "doc-09-cp158-consumer-protection-code.json"
    cp158_document = json.loads(cp158_path.read_text(encoding="utf-8"))
    assert "supersedes" not in cp158_document
