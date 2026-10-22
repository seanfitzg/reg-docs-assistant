# The heading_sections chunking strategy (ADR-0014): splits a narrative
# document into Chunks at bold heading lines, with the locator pairing the
# heading text with its starting page (ADR-0015) -- e.g. "Purpose (p. 5)".
# Unlike clause_numbered's bare clause numbers, a heading alone isn't unique
# or locatable in a long document, so the page number earns its place.
#
# Known limitation, found running this against the real DP8 PDF: a cover-page
# title, or any other lone bold line that isn't a section heading (e.g. one
# bold Table-of-Contents entry among regular ones), is misdetected as a
# heading, since the only signal is "every span on the line is bold".
# Everything up to the next real heading (for a cover page, possibly the whole
# Table of Contents) becomes that spurious heading's chunk text. A reliable
# fix needs page-based front-matter exclusion or a heading-length heuristic,
# both design decisions of their own.

from pathlib import Path

from regdocs_ingestion.clean import (
    apply_cleanup_flags,
    strip_headers_footers_and_page_numbers_from_layout,
)
from regdocs_ingestion.extract import extract_pages_with_headings


def chunk(pages: list[list[dict]]) -> list[dict]:
    chunks = []

    # The section currently being built. current_locator is None until the
    # first heading, so lines before it (cover-page blurb, etc.) belong to no
    # section and are dropped.
    current_locator = None
    current_lines: list[str] = []

    def flush_current_section():
        if current_locator is None:
            return
        text = "\n".join(current_lines).strip()
        # A heading immediately followed by another isn't a citable unit, as
        # with clause_numbered's empty-chunk guard.
        if text:
            chunks.append({"locator": current_locator, "text": text})

    for page_number, lines in enumerate(pages, start=1):
        for line in lines:
            if line["is_heading"]:
                # A new heading finishes the previous section.
                flush_current_section()
                current_locator = f"{line['text']} (p. {page_number})"
                current_lines = []
            elif current_locator is not None:
                current_lines.append(line["text"])

    # The last section has no following heading to trigger its flush.
    flush_current_section()

    return chunks


def chunk_document(
    pdf_path: Path, cleanup_flags: list[dict] | None = None
) -> list[dict]:
    # cleanup_flags comes from a manifest entry (ADR-0016, issue #9;
    # parameterised in #13), e.g. {"type": "navigation_chrome", "pattern":
    # "Annex \\d", "minimum_matches": 4}. DP8 sets none, so
    # apply_cleanup_flags() is a no-op; DP7 names "navigation_chrome" to strip
    # its Annex-nav footer.
    raw_pages = extract_pages_with_headings(pdf_path)
    cleaned_pages = strip_headers_footers_and_page_numbers_from_layout(raw_pages)
    cleaned_pages = apply_cleanup_flags(cleaned_pages, cleanup_flags or [])
    return chunk(cleaned_pages)
