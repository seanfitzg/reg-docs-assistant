# The clause_numbered chunking strategy (ADR-0014): splits a document's
# cleaned text into Chunks at decimal clause numbers like "1.1", using the
# bare number as the locator (a clause number is already directly searchable
# in the source PDF, so unlike heading_sections/academic_sections it needs no
# page number -- Q5).

import re
from pathlib import Path

from regdocs_ingestion.clean import strip_headers_footers_and_page_numbers
from regdocs_ingestion.extract import extract_pages

# ^            start of a line (re.MULTILINE, so every line, not just the text)
# (\d{1,2})    the "chapter" part, 1-2 digits
# \.           a literal dot
# (\d{1,3})    the "paragraph" part, 1-3 digits
# \.?          an optional trailing dot (CP54 writes both "1.10" and "1.9.")
# \s*          trailing whitespace, consumed but not captured
CLAUSE_NUMBER_PATTERN = re.compile(r"^(\d{1,2}\.\d{1,3})\.?\s*", re.MULTILINE)


def chunk(text: str) -> list[dict]:
    # finditer, not findall, because each match's position is needed to know
    # where one clause's text ends and the next begins. Collected to a list to
    # look ahead by index.
    matches = list(CLAUSE_NUMBER_PATTERN.finditer(text))

    chunks = []
    for index, match in enumerate(matches):
        # The trailing "." is outside the capturing group, so it's excluded.
        locator = match.group(1)

        # This clause's text starts after the number, dot and whitespace...
        chunk_start = match.end()
        # ...and runs to the next clause number, or the end of the text.
        if index + 1 < len(matches):
            chunk_end = matches[index + 1].start()
        else:
            chunk_end = len(text)

        chunk_text = text[chunk_start:chunk_end].strip()

        # A clause number with no text after it (two markers back-to-back)
        # isn't a real citable unit.
        if chunk_text:
            chunks.append({"locator": locator, "text": chunk_text})

    return chunks


def chunk_document(
    pdf_path: Path, cleanup_flags: list[dict] | None = None
) -> list[dict]:
    # Every strategy exposes this same signature so pipeline.py can call
    # whichever one a manifest entry names without knowing its extraction
    # needs.
    #
    # cleanup_flags (ADR-0016, issue #9) is accepted only for that uniform
    # signature. clean.py's manifest-flagged functions understand only the
    # list[list[dict]] layout shape, not the plain per-page text this strategy
    # works from.
    raw_pages = extract_pages(pdf_path)
    cleaned_pages = strip_headers_footers_and_page_numbers(raw_pages)
    full_text = "\n".join(cleaned_pages)
    return chunk(full_text)
