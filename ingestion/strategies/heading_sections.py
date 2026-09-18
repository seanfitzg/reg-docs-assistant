# The heading_sections chunking strategy (ADR-0014): splits a narrative
# document into Chunks at bold heading lines, with the locator pairing the
# heading text with the page it starts on (ADR-0015) -- e.g.
# "Purpose (p. 5)". Unlike clause_numbered's bare clause numbers, a heading
# alone isn't unique or locatable in a long document, so the page number
# earns its place here.
#
# Known limitation, found running this against the real DP8 PDF: a
# document's cover-page title, and any other lone bold line that isn't
# really a section heading (e.g. one bold Table-of-Contents entry among
# otherwise-regular ones), gets misdetected as a heading the same way a
# real one does -- there's no signal here beyond "every span on the line is
# bold" to tell them apart. When that happens, everything between it and
# the next real heading (which, for a cover page, can be the entire
# Table of Contents) becomes that spurious heading's chunk text. This
# wasn't fixed here: a reliable fix needs either page-based front-matter
# exclusion or a heading-length heuristic, both of which are real design
# decisions in their own right, not something to guess at unreviewed mid-
# ticket.

from pathlib import Path

from clean import apply_cleanup_flags, strip_headers_footers_and_page_numbers_from_layout
from extract import extract_pages_with_headings


def chunk(pages: list[list[dict]]) -> list[dict]:
    chunks = []

    # These two track "the section currently being built" as we walk
    # through every line on every page, in order. current_locator is None
    # until the first heading is seen -- any lines before that (cover-page
    # blurb, etc.) belong to no section and are simply never appended
    # anywhere.
    current_locator = None
    current_lines: list[str] = []

    # A nested "def" -- a function defined inside another function -- is
    # Python's equivalent of a C# local function. It can read (though not,
    # without an extra "nonlocal" declaration this one doesn't need,
    # reassign) the enclosing function's variables directly, which is why
    # flush_current_section() below can see current_locator and
    # current_lines without them being passed in as parameters.
    def flush_current_section():
        if current_locator is None:
            return
        text = "\n".join(current_lines).strip()
        # A heading immediately followed by another heading (nothing real
        # in between) isn't a citable unit -- same reasoning as
        # clause_numbered's equivalent empty-chunk guard.
        if text:
            chunks.append({"locator": current_locator, "text": text})

    for page_number, lines in enumerate(pages, start=1):
        for line in lines:
            if line["is_heading"]:
                # Starting a new section means the previous one is
                # finished -- flush it before overwriting current_locator.
                flush_current_section()
                current_locator = f"{line['text']} (p. {page_number})"
                current_lines = []
            elif current_locator is not None:
                current_lines.append(line["text"])

    # The loop above only flushes when a *new* heading starts a section;
    # the very last section in the document never gets that trigger, so it
    # needs flushing once more after the loop ends.
    flush_current_section()

    return chunks


def chunk_document(pdf_path: Path, cleanup_flags: list[str] | None = None) -> list[dict]:
    # cleanup_flags comes straight from a manifest entry's "cleanup_flags"
    # (ADR-0016, issue #9) -- e.g. DP8's own manifest entry never sets it,
    # so it stays None/empty and apply_cleanup_flags() below is a no-op,
    # while DP7's entry names "navigation_chrome" to strip its Annex-nav
    # footer. Every strategy's chunk_document accepts this same parameter
    # (pipeline.py always passes it) even though clause_numbered and
    # academic_sections don't currently act on it -- see their own modules.
    raw_pages = extract_pages_with_headings(pdf_path)
    cleaned_pages = strip_headers_footers_and_page_numbers_from_layout(raw_pages)
    cleaned_pages = apply_cleanup_flags(cleaned_pages, cleanup_flags or [])
    return chunk(cleaned_pages)
