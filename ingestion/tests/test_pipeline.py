# End-to-end tests for pipeline.py: manifest -> extract -> clean -> chunk ->
# validate -> write, run against real corpus PDFs -- CP54 for
# clause_numbered (issue #5), DP8 for heading_sections (issue #6), RTP07/19
# for academic_sections (issue #7), DP7 and FSR for manifest-flagged cleanup
# (ADR-0016, issue #9), and the full 20-document corpus (issue #10). These are
# the only tests exercising every module together; the others are unit tests
# for one module each.
#
# The corpus isn't committed to git (see corpus/SOURCES.md), so these tests
# skip rather than fail when a PDF isn't present locally.

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
# The issue #10 tests need every PDF the manifest declares, so they get a
# separate guard to skip on a partial corpus. Checking each declared filename
# (not counting *.pdf files) stays correct if the directory has stray PDFs.
requires_full_corpus = pytest.mark.skipif(
    not all(
        (CORPUS_DIR / entry["filename"]).exists()
        for entry in load_manifest(MANIFEST_PATH)
    ),
    reason="corpus PDFs aren't committed to git -- see corpus/SOURCES.md to download them",
)


def _entry_for(entries: list[dict], filename: str) -> dict:
    return next(e for e in entries if e["filename"] == filename)


def test_load_manifest_reads_all_twenty_entries():
    entries = load_manifest(MANIFEST_PATH)

    assert len(entries) == 20

    cp54 = _entry_for(
        entries, "04-cp54-second-consultation-consumer-protection-code.pdf"
    )
    assert cp54["chunking_strategy"] == "clause_numbered"
    # CP54 is the second consultation on the Code review CP47 opened, so it
    # links back to CP47 (ADR-0002), confirmed from both covers (issue #10).
    assert cp54["supersedes"] == "doc-03-cp47-review-of-consumer-protection-code"

    cp158 = _entry_for(entries, "09-cp158-consumer-protection-code.pdf")
    # heading_sections, not clause_numbered (issue #10): unlike CP54/CP131,
    # CP158's prose isn't consistently clause-numbered. clause_numbered
    # produces duplicate locators (a "2.1"-"3.5" run from the Table of
    # Contents' dotted lines, then a real run for the body) and one
    # 43,762-character mega-chunk, whereas heading_sections finds 98 clean
    # chunks (each under ~7KB) from its titled sections.
    assert cp158["chunking_strategy"] == "heading_sections"
    # CP158 cites "Our 2022 Code Review Discussion Paper" as its predecessor,
    # not DP7 (a narrower 2017 digitalisation paper). The 2022 paper isn't in
    # the corpus, so no real Document id can be superseded; setting one anyway
    # would record a factually wrong link, worse than none (ADR-0010's "wrong
    # but plausible beats obviously missing" reasoning, applied to Supersedes).
    assert cp158["supersedes"] is None

    dp8 = _entry_for(entries, "12-dp8-outsourcing-findings-and-issues.pdf")
    assert dp8["chunking_strategy"] == "heading_sections"

    rtp = _entry_for(
        entries, "19-rtp-07rt19-money-market-funds-unconventional-policy.pdf"
    )
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
    document, chunks = build_document_and_chunks(
        _entry_for(entries, CP54_FILENAME), CORPUS_DIR
    )

    document_schema = load_schema("document.schema.json")
    validate_against_schema(document, document_schema)


@requires_cp54
def test_build_document_and_chunks_produces_schema_valid_chunks():
    entries = load_manifest(MANIFEST_PATH)
    document, chunks = build_document_and_chunks(
        _entry_for(entries, CP54_FILENAME), CORPUS_DIR
    )

    chunk_schema = load_schema("chunk.schema.json")
    assert len(chunks) > 0
    for one_chunk in chunks:
        validate_against_schema(one_chunk, chunk_schema)


@requires_cp54
def test_document_id_is_derived_and_generation_is_active():
    entries = load_manifest(MANIFEST_PATH)
    document, chunks = build_document_and_chunks(
        _entry_for(entries, CP54_FILENAME), CORPUS_DIR
    )

    assert document["id"] == "doc-04-cp54-second-consultation-consumer-protection-code"
    # Every chunk belongs to the Document's active generation (ADR-0004),
    # proving the pointer is wired up, not just present.
    for one_chunk in chunks:
        assert (
            one_chunk["chunking_generation_id"]
            == document["active_chunking_generation_id"]
        )
        assert one_chunk["document_id"] == document["id"]


@requires_cp54
def test_chunk_locators_are_bare_clause_numbers_not_page_decorated():
    entries = load_manifest(MANIFEST_PATH)
    document, chunks = build_document_and_chunks(
        _entry_for(entries, CP54_FILENAME), CORPUS_DIR
    )

    # A bare clause number like "1.8", not "1.8 (p. 7)": heading_sections/
    # academic_sections locators are page-decorated (ADR-0015); clause_numbered
    # ones deliberately aren't (Q5 of the grilling session).
    known_real_clause = next(c for c in chunks if c["locator"] == "1.8")
    assert "(p." not in known_real_clause["locator"]


@requires_cp54
def test_repeated_header_is_stripped_from_every_chunk():
    entries = load_manifest(MANIFEST_PATH)
    document, chunks = build_document_and_chunks(
        _entry_for(entries, CP54_FILENAME), CORPUS_DIR
    )

    # "Consultation Paper CP 54" is the running header on every page, so
    # header stripping (ADR-0016) should keep it out of every chunk.
    for one_chunk in chunks:
        assert "Consultation Paper CP 54" not in one_chunk["text"]


# ---- heading_sections: DP8 (issue #6) ----


@requires_dp8
def test_dp8_build_document_and_chunks_produces_schema_valid_output():
    entries = load_manifest(MANIFEST_PATH)
    document, chunks = build_document_and_chunks(
        _entry_for(entries, DP8_FILENAME), CORPUS_DIR
    )

    validate_against_schema(document, load_schema("document.schema.json"))
    chunk_schema = load_schema("chunk.schema.json")
    assert len(chunks) > 0
    for one_chunk in chunks:
        validate_against_schema(one_chunk, chunk_schema)


@requires_dp8
def test_dp8_document_id_is_derived_and_generation_is_active():
    entries = load_manifest(MANIFEST_PATH)
    document, chunks = build_document_and_chunks(
        _entry_for(entries, DP8_FILENAME), CORPUS_DIR
    )

    assert document["id"] == "doc-12-dp8-outsourcing-findings-and-issues"
    for one_chunk in chunks:
        assert (
            one_chunk["chunking_generation_id"]
            == document["active_chunking_generation_id"]
        )
        assert one_chunk["document_id"] == document["id"]


@requires_dp8
def test_dp8_chunk_locators_pair_a_real_heading_with_a_page_number():
    entries = load_manifest(MANIFEST_PATH)
    document, chunks = build_document_and_chunks(
        _entry_for(entries, DP8_FILENAME), CORPUS_DIR
    )

    # "Purpose" is a real heading on page 5, so the strategy found a bold
    # heading and decorated it with a page number (ADR-0015).
    purpose_chunk = next(c for c in chunks if c["locator"].startswith("Purpose"))
    assert purpose_chunk["locator"] == "Purpose (p. 5)"


@requires_dp8
def test_dp8_repeated_header_and_page_footer_are_stripped_from_every_chunk():
    entries = load_manifest(MANIFEST_PATH)
    document, chunks = build_document_and_chunks(
        _entry_for(entries, DP8_FILENAME), CORPUS_DIR
    )

    # Checks whole *lines*, not substrings: "Central Bank of Ireland" and
    # "Outsourcing" appear constantly in body prose. Only a standalone line is
    # the running header.
    for one_chunk in chunks:
        chunk_lines = one_chunk["text"].splitlines()
        assert "Central Bank of Ireland" not in chunk_lines
        assert "Outsourcing" not in chunk_lines
        # DP8's footer is "Page <N>" on its own line, proving the
        # "Page "-prefixed rule fires on the real document, not just in
        # test_clean.py.
        assert not any(
            line.startswith("Page ") and line[5:].isdigit() for line in chunk_lines
        )


# ---- academic_sections: RTP07/19 (issue #7) ----


@requires_rtp
def test_rtp_build_document_and_chunks_produces_schema_valid_output():
    entries = load_manifest(MANIFEST_PATH)
    document, chunks = build_document_and_chunks(
        _entry_for(entries, RTP_FILENAME), CORPUS_DIR
    )

    validate_against_schema(document, load_schema("document.schema.json"))
    chunk_schema = load_schema("chunk.schema.json")
    assert len(chunks) > 0
    for one_chunk in chunks:
        validate_against_schema(one_chunk, chunk_schema)


@requires_rtp
def test_rtp_document_id_is_derived_and_generation_is_active():
    entries = load_manifest(MANIFEST_PATH)
    document, chunks = build_document_and_chunks(
        _entry_for(entries, RTP_FILENAME), CORPUS_DIR
    )

    assert (
        document["id"] == "doc-19-rtp-07rt19-money-market-funds-unconventional-policy"
    )
    for one_chunk in chunks:
        assert (
            one_chunk["chunking_generation_id"]
            == document["active_chunking_generation_id"]
        )
        assert one_chunk["document_id"] == document["id"]


@requires_rtp
def test_rtp_chunk_locators_pair_a_real_heading_with_a_page_number():
    entries = load_manifest(MANIFEST_PATH)
    document, chunks = build_document_and_chunks(
        _entry_for(entries, RTP_FILENAME), CORPUS_DIR
    )

    # "Introduction" is a real single-line heading on page 4 (ADR-0015).
    introduction_chunk = next(
        c for c in chunks if c["locator"] == "Introduction (p. 4)"
    )
    assert introduction_chunk["text"]


@requires_rtp
def test_rtp_a_heading_wrapped_across_two_bold_lines_is_joined_in_the_real_pdf():
    entries = load_manifest(MANIFEST_PATH)
    document, chunks = build_document_and_chunks(
        _entry_for(entries, RTP_FILENAME), CORPUS_DIR
    )

    # Appendix A's heading is two consecutive bold lines ("A Sources and
    # Construction of Variables Used in Panel" / "Regressions"), confirming
    # academic_sections' join fires on the real document, not just the
    # synthetic fixture.
    appendix_chunk = next(c for c in chunks if c["locator"].startswith("A Sources"))
    assert appendix_chunk["locator"] == (
        "A Sources and Construction of Variables Used in Panel Regressions (p. 26)"
    )


@requires_rtp
def test_rtp_extracted_text_recovers_ligatured_words_cleanly():
    # pypdf corrupted this document's glyphs/ligatures (see extract.py);
    # pymupdf's fix is what unblocked #7. pymupdf keeps an "fi" pair as one
    # ligature codepoint (U+FB01), so a plain search for "certificates" won't
    # match; NFKC normalization decomposes it back to letters. Finding the
    # word proves the text is recoverable Unicode, not corrupted, inside the
    # real pipeline.
    entries = load_manifest(MANIFEST_PATH)
    document, chunks = build_document_and_chunks(
        _entry_for(entries, RTP_FILENAME), CORPUS_DIR
    )

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
    document, chunks = build_document_and_chunks(
        _entry_for(entries, DP7_FILENAME), CORPUS_DIR
    )

    validate_against_schema(document, load_schema("document.schema.json"))
    chunk_schema = load_schema("chunk.schema.json")
    assert len(chunks) > 0
    for one_chunk in chunks:
        validate_against_schema(one_chunk, chunk_schema)


@requires_dp7
def test_dp7_navigation_chrome_footer_is_stripped_from_every_chunk():
    entries = load_manifest(MANIFEST_PATH)
    document, chunks = build_document_and_chunks(
        _entry_for(entries, DP7_FILENAME), CORPUS_DIR
    )

    # DP7's Annex pages carry a nav-breadcrumb footer ("Annex 1 page 1 of 3 >
    # | Annex 2  | Annex 3  | Annex 4"). If the navigation_chrome flag works,
    # no chunk contains its "page X of Y" fragment on any Annex.
    for one_chunk in chunks:
        for total in (2, 3):
            for page_number in range(1, total + 1):
                assert f"page {page_number} of {total}" not in one_chunk["text"]


@requires_dp7
def test_dp7_a_real_annex_toc_entry_survives_the_navigation_chrome_flag():
    # The flag must be specific to the nav footer, not delete legitimate
    # content like DP7's Table of Contents entry "Annex 2".
    entries = load_manifest(MANIFEST_PATH)
    document, chunks = build_document_and_chunks(
        _entry_for(entries, DP7_FILENAME), CORPUS_DIR
    )

    assert any("Annex 2" in one_chunk["text"] for one_chunk in chunks)


# ---- manifest-flagged cleanup: FSR "duplicate_section_removal" (ADR-0016,
# ---- issue #9, parameterised in issue #13) ----


@requires_fsr
def test_fsr_build_document_and_chunks_produces_schema_valid_output():
    entries = load_manifest(MANIFEST_PATH)
    document, chunks = build_document_and_chunks(
        _entry_for(entries, FSR_FILENAME), CORPUS_DIR
    )

    validate_against_schema(document, load_schema("document.schema.json"))
    chunk_schema = load_schema("chunk.schema.json")
    assert len(chunks) > 0
    for one_chunk in chunks:
        validate_against_schema(one_chunk, chunk_schema)


@requires_fsr
def test_fsr_irish_duplicate_sections_produce_no_chunks_of_their_own():
    entries = load_manifest(MANIFEST_PATH)
    document, chunks = build_document_and_chunks(
        _entry_for(entries, FSR_FILENAME), CORPUS_DIR
    )

    # "Réamhrá"/"Forbhreathnú" (Irish for "Preface"/"Overview") head the Irish
    # duplicate content. If duplicate_section_removal works (start_heading is
    # "Réamhrá"), neither survives as a locator.
    locators = [one_chunk["locator"] for one_chunk in chunks]
    assert not any(locator.startswith("Réamhrá") for locator in locators)
    assert not any(locator.startswith("Forbhreathnú") for locator in locators)


@requires_fsr
def test_fsr_english_content_either_side_of_the_irish_section_survives():
    # Only the Irish span goes: the English content before ("Preface") and
    # after ("Global risk assessment") it survives.
    entries = load_manifest(MANIFEST_PATH)
    document, chunks = build_document_and_chunks(
        _entry_for(entries, FSR_FILENAME), CORPUS_DIR
    )

    locators = [one_chunk["locator"] for one_chunk in chunks]
    assert any(locator.startswith("Preface") for locator in locators)
    assert any(locator.startswith("Global risk assessment") for locator in locators)


# ---- full 20-document corpus (issue #10) ----
#
# Everything above exercises one document per strategy/cleanup flag; these
# check the corpus as a *whole*: every document makes it through (the
# acceptance criterion "no document silently fails or is skipped without a
# surfaced reason"), and the supersedes links resolve end to end.


@requires_full_corpus
def test_run_pipeline_writes_validated_output_files_for_every_document(tmp_path):
    output_dir = tmp_path / "output"

    manifest_entries = load_manifest(MANIFEST_PATH)
    results = run_pipeline(MANIFEST_PATH, CORPUS_DIR, output_dir)

    # run_pipeline returns one pair per successfully ingested entry
    # (ADR-0019), so matching the manifest's count proves all 20 got through.
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
def test_run_pipeline_surfaces_no_silent_failures_across_the_full_corpus(
    tmp_path, caplog
):
    # Failure isolation (ADR-0019, issue #8) exists so one bad document can't
    # take down the batch, but against the *real* corpus nothing should
    # trigger it. run_pipeline logs at ERROR only when it skips an entry, so
    # no ERROR records is a direct check against "no document silently fails".
    output_dir = tmp_path / "output"
    with caplog.at_level(logging.ERROR):
        run_pipeline(MANIFEST_PATH, CORPUS_DIR, output_dir)

    assert caplog.records == []


@requires_full_corpus
def test_run_pipeline_writes_the_supersedes_link_for_cp54(tmp_path):
    output_dir = tmp_path / "output"

    run_pipeline(MANIFEST_PATH, CORPUS_DIR, output_dir)

    cp54_path = (
        output_dir
        / "documents"
        / "doc-04-cp54-second-consultation-consumer-protection-code.json"
    )
    cp54_document = json.loads(cp54_path.read_text(encoding="utf-8"))
    assert (
        cp54_document["supersedes"] == "doc-03-cp47-review-of-consumer-protection-code"
    )


@requires_full_corpus
def test_run_pipeline_writes_no_supersedes_key_for_cp158(tmp_path):
    # CP158 deliberately has no supersedes link (see
    # test_load_manifest_reads_all_twenty_entries). The key must be absent
    # from the written JSON, not null, which the schema's "type": "string"
    # would reject.
    output_dir = tmp_path / "output"

    run_pipeline(MANIFEST_PATH, CORPUS_DIR, output_dir)

    cp158_path = output_dir / "documents" / "doc-09-cp158-consumer-protection-code.json"
    cp158_document = json.loads(cp158_path.read_text(encoding="utf-8"))
    assert "supersedes" not in cp158_document
