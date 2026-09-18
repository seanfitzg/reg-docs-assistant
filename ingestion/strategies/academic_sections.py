# The academic_sections chunking strategy (ADR-0014): splits a Research
# Technical Paper into Chunks at bold heading lines, with the locator
# pairing the heading text with the page it starts on (ADR-0015) -- e.g.
# "Literature Review (p. 7)". It shares heading_sections' underlying
# signal -- a section title is the only fully-bold line, the same way DP8's
# headings are -- because that's genuinely what pymupdf's extraction shows
# for this document too (see the module-level exploration that produced
# this ticket): despite the issue's "1 Introduction" example, this PDF's
# main section titles don't carry a leading digit as extractable text at
# all; only its appendices do ("A Sources...", "B Figures", "C Tables").
#
# One real difference from heading_sections, found by inspecting the actual
# RTP07/19 PDF rather than assumed up front: a heading here can wrap across
# more than one bold line with nothing in between -- this document's own
# two-line title on page 2, and its "A Sources and Construction of
# Variables Used in Panel" / "Regressions" appendix heading on page 26, are
# both a single heading split across two consecutive bold lines, not two
# separate sections. heading_sections' rule for back-to-back heading lines
# (drop the first as empty, keep the second) was written for DP8, where a
# spurious bold cover-page/ToC line can sit directly before a real heading
# -- exactly the opposite shape. Applying that rule here would silently
# lose the first half of the Appendix A locator. So this module instead
# *joins* consecutive heading lines into one heading, using the page the
# first line started on.
#
# This is its own trade-off, not a strictly better rule: if this document
# ever contained a genuinely empty heading directly followed by a real,
# unrelated one (DP8's shape), this would wrongly merge them into one
# locator instead of dropping the empty one. Every back-to-back heading
# pair actually found in RTP07/19 was a wrapped title, never that DP8
# shape, so the join rule is what was implemented -- flagged here rather
# than silently assumed to generalize to some other academic paper.
#
# The same join rule also fires on a case that isn't a wrapped title at
# all: page 9's top-level "Money Market Funds" section heading is directly
# followed by its own first subsection heading, "Regulation and
# Institutional Setting" (a smaller font, but still a fully-bold line),
# with no lead-in paragraph between them. There's no signal available here
# (extract_pages_with_headings exposes is_heading as a plain bool, not font
# size) to tell "a section with no preamble, going straight into its first
# subsection" apart from "one heading wrapped across two lines" -- both are
# just two consecutive bold lines with nothing between them. The result is
# a merged, slightly odd-looking locator ("Money Market Funds Regulation
# and Institutional Setting (p. 9)") rather than two separate ones. Still a
# valid, citable page anchor, just not a granularity split -- distinguishing
# heading levels would mean extract_pages_with_headings starting to expose
# font size too, a real design decision of its own, not something to add
# unreviewed mid-ticket.
#
# A heading run is only allowed to continue within a single page (see the
# same-page check in chunk() below). This matters because chunk() never
# sees the *raw* pages -- chunk_document() strips boilerplate (running
# headers/footers, bare page numbers, ADR-0016) first. A footer stripped
# from the bottom of page N and a header stripped from the top of page
# N+1 would otherwise make two genuinely unrelated headings either side of
# a page break look exactly like one back-to-back run, the same shape as a
# real wrapped heading -- and get wrongly joined into one bogus locator.
# Both real wraps actually found in this document (the title on page 2,
# the Appendix A heading on page 26) wrap within a single page, so this
# restriction closes that hole without losing either real case; it would
# only cost a heading that genuinely wraps *across* a page boundary, which
# this document never does.
#
# Known, not fixed here: a title-page line that's bold for styling reasons
# (this document's own title, e.g.) still gets mistaken for a real section
# heading the same way heading_sections documents for DP8's cover page --
# sweeping the author/affiliation blurb into that heading's chunk text.
# Separately, clean.py's boilerplate-line stripping (shared with
# heading_sections, ADR-0016) treats any line repeated on 3+ pages as a
# running header/footer; this document's regression-result tables repeat
# short column labels ("CORP-SPREAD", "(1)", "Yes", ...) across many pages,
# so those get stripped from chunk text as if they were boilerplate. Both
# are pre-existing heuristics being applied to a document shape they
# weren't designed against -- real limitations, not something to patch
# with an unreviewed heuristic mid-ticket.

from pathlib import Path

from clean import strip_headers_footers_and_page_numbers_from_layout
from extract import extract_pages_with_headings


def chunk(pages: list[list[dict]]) -> list[dict]:
    chunks = []

    current_locator = None
    current_lines: list[str] = []

    # Bold lines accumulate here until it's known whether the *next* line
    # continues the same heading (another bold line) or starts the
    # section's body (a non-bold line) -- a heading isn't complete, and
    # can't be turned into a locator, until that's known.
    pending_heading_lines: list[str] = []
    # "int | None" is a union type hint: this variable is either an int or
    # None -- Python's built-in spelling of C#'s "int?" (Nullable<int>).
    # It starts out None (no heading run open yet) and gets set to a real
    # page number once the first heading line of a run is seen.
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
                    # Starting a fresh heading run -- either this is the
                    # very first heading line seen, or a run was left open
                    # on an *earlier* page (module comment: a run may only
                    # continue within a single page). In that second case
                    # the open run never reached a body line, so it holds
                    # no real section -- there's nothing to flush for it,
                    # only whatever *finished* section came before it.
                    #
                    # Clearing current_locator here (not just flushing it)
                    # matters: if *this* new run never reaches a body line
                    # either (e.g. it's the last thing in the document), the
                    # final flush_current_section() call after the loop must
                    # find nothing left to re-flush, rather than emitting
                    # the just-flushed previous section a second time.
                    flush_current_section()
                    current_locator = None
                    current_lines = []
                    pending_heading_lines = []
                    pending_heading_page = page_number
                pending_heading_lines.append(line["text"])
            else:
                if pending_heading_lines:
                    # A non-heading line arriving means the heading run
                    # that came before it is complete -- join its line(s)
                    # with a space into one locator, anchored to the page
                    # the *first* of those lines was on.
                    current_locator = (
                        f"{' '.join(pending_heading_lines)} (p. {pending_heading_page})"
                    )
                    current_lines = []
                    pending_heading_lines = []
                if current_locator is not None:
                    current_lines.append(line["text"])

    # A heading run still "pending" when the document ends -- the very
    # last lines on the last page were all bold, with no body text ever
    # following -- never got turned into a locator above, so there's
    # nothing to flush for it; only a *finished* section (one that reached
    # at least one non-heading line) can produce a chunk.
    flush_current_section()

    return chunks


def chunk_document(pdf_path: Path, cleanup_flags: list[dict] | None = None) -> list[dict]:
    # cleanup_flags (ADR-0016, issue #9) is accepted here purely for the
    # uniform chunk_document(pdf_path, cleanup_flags) shape every strategy
    # exposes (see clause_numbered.chunk_document) -- no manifest entry
    # using academic_sections declares any cleanup_flags yet, so this
    # strategy doesn't act on it.
    raw_pages = extract_pages_with_headings(pdf_path)
    cleaned_pages = strip_headers_footers_and_page_numbers_from_layout(raw_pages)
    return chunk(cleaned_pages)
