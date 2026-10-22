# The academic_sections chunking strategy (ADR-0014): splits a Research
# Technical Paper into Chunks at bold heading lines, with the locator pairing
# the heading text with its starting page (ADR-0015) -- e.g.
# "Literature Review (p. 7)". It shares heading_sections' signal (a section
# title is a fully-bold line) because that's what pymupdf shows for this
# document: despite the issue's "1 Introduction" example, the main section
# titles carry no leading digit as extractable text; only the appendices do
# ("A Sources...", "B Figures", "C Tables").
#
# Difference from heading_sections, found by inspecting the RTP07/19 PDF: a
# heading can wrap across more than one bold line (the two-line title on page
# 2, the Appendix A heading on page 26). heading_sections drops the first of
# two back-to-back heading lines as empty, which was written for DP8, where a
# spurious bold cover-page/ToC line can sit directly before a real heading --
# the opposite shape. Applying that here would lose half the Appendix A
# locator, so this module *joins* consecutive heading lines into one heading,
# anchored to the first line's page.
#
# Trade-off: if this document ever had a genuinely empty heading directly
# before an unrelated real one (DP8's shape), they'd be wrongly merged. Every
# back-to-back pair found in RTP07/19 was a wrapped title, so the join rule
# was implemented; it may not generalize to other academic papers.
#
# The join also fires where a title isn't wrapped: page 9's "Money Market
# Funds" heading is directly followed by its first subsection heading,
# "Regulation and Institutional Setting" (smaller font, still fully bold).
# extract_pages_with_headings exposes is_heading as a bool, not font size, so
# that can't be told apart from a wrapped heading. The result is a merged
# locator ("Money Market Funds Regulation and Institutional Setting (p. 9)"):
# still a valid page anchor, just coarser. Distinguishing heading levels would
# mean exposing font size, a design decision of its own.
#
# A heading run may only continue within a single page (see the same-page
# check in chunk()). chunk() sees pages after boilerplate stripping
# (ADR-0016), so a footer stripped from the bottom of page N and a header
# stripped from the top of page N+1 would make two unrelated headings across a
# page break look like one wrapped heading and get joined. Both real wraps
# found are within a page, so this loses nothing; it would only miss a heading
# that wraps across a page boundary, which this document never does.
#
# Known, not fixed here: a title-page line that's bold for styling is still
# mistaken for a section heading, as heading_sections documents for DP8's
# cover page, sweeping the author/affiliation blurb into that chunk. Also,
# clean.py's boilerplate stripping (any line repeated on 3+ pages) removes
# this document's repeated regression-table labels ("CORP-SPREAD", "(1)",
# "Yes", ...) from chunk text. Both are existing heuristics applied to a
# document shape they weren't designed for.

from pathlib import Path

from regdocs_ingestion.clean import strip_headers_footers_and_page_numbers_from_layout
from regdocs_ingestion.extract import extract_pages_with_headings


def chunk(pages: list[list[dict]]) -> list[dict]:
    chunks = []

    current_locator = None
    current_lines: list[str] = []

    # Bold lines accumulate here until it's known whether the next line
    # continues the heading (another bold line) or starts the body (a
    # non-bold line); only then can the heading become a locator.
    pending_heading_lines: list[str] = []
    # None until the first line of a heading run is seen.
    pending_heading_page: int | None = None

    def flush_current_section():
        if current_locator is None:
            return
        text = "\n".join(current_lines).strip()
        if text:
            chunks.append({"locator": current_locator, "text": text})

    for page_number, lines in enumerate(pages, start=1):
        for line in lines:
            if line["is_heading"]:
                if not pending_heading_lines or page_number != pending_heading_page:
                    # A fresh heading run: the first one seen, or a run left
                    # open on an earlier page (a run may only continue within
                    # a page). That open run never reached a body line, so it
                    # holds no section; only the section that finished before
                    # it needs flushing.
                    #
                    # current_locator is cleared, not just flushed: if this
                    # new run never reaches a body line either (e.g. it ends
                    # the document), the final flush must not emit the
                    # previous section a second time.
                    flush_current_section()
                    current_locator = None
                    current_lines = []
                    pending_heading_lines = []
                    pending_heading_page = page_number
                pending_heading_lines.append(line["text"])
            else:
                if pending_heading_lines:
                    # A body line completes the preceding heading run: join
                    # its lines into one locator, anchored to the page of the
                    # first line.
                    current_locator = (
                        f"{' '.join(pending_heading_lines)} (p. {pending_heading_page})"
                    )
                    current_lines = []
                    pending_heading_lines = []
                if current_locator is not None:
                    current_lines.append(line["text"])

    # A heading run still pending at the end (the last lines were all bold)
    # never became a locator, so there's nothing to flush for it; only a
    # finished section (one with a body line) produces a chunk.
    flush_current_section()

    return chunks


def chunk_document(
    pdf_path: Path, cleanup_flags: list[dict] | None = None
) -> list[dict]:
    # cleanup_flags (ADR-0016, issue #9) is accepted only for the uniform
    # strategy signature; no academic_sections manifest entry declares any, so
    # it isn't acted on.
    raw_pages = extract_pages_with_headings(pdf_path)
    cleaned_pages = strip_headers_footers_and_page_numbers_from_layout(raw_pages)
    return chunk(cleaned_pages)
