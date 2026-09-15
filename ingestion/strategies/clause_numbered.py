# The clause_numbered chunking strategy (ADR-0014): splits a document's
# cleaned text into Chunks at decimal clause numbers like "1.1", using the
# bare number as the locator (a clause number is already directly
# searchable in the source PDF, so unlike heading_sections/
# academic_sections it needs no page number decoration -- Q5).

import re
from pathlib import Path

from clean import strip_headers_footers_and_page_numbers
from extract import extract_pages

# re.compile(...) pre-builds a regular expression once, rather than
# re-parsing the pattern string every time it's used -- comparable to a
# static readonly Regex field in C#.
#
# Pattern breakdown:
#   ^            start of a line (only matches there, because of re.MULTILINE)
#   (\d{1,2})    the "chapter" part: 1-2 digits, captured as group 1
#   \.           a literal dot
#   (\d{1,3})    the "paragraph" part: 1-3 digits, captured as group 2
#   \.?          an optional trailing dot (CP54 writes both "1.10" and "1.9.")
#   \s*          any whitespace that follows (space, or nothing before a
#                newline), consumed but not captured
#
# re.MULTILINE makes "^" match at the start of every line in the text, not
# just the very start of the whole string -- without it, only a clause
# number on line 1 would ever match.
CLAUSE_NUMBER_PATTERN = re.compile(r"^(\d{1,2}\.\d{1,3})\.?\s*", re.MULTILINE)


def chunk(text: str) -> list[dict]:
    # .finditer(...) returns every match in the text as an iterator of
    # Match objects (position + captured groups), unlike .findall(...)
    # which would throw away each match's position -- and we need the
    # position to know where one clause's text ends and the next begins.
    # list(...) eagerly collects that iterator so we can look ahead by
    # index (matches[i + 1]) below.
    matches = list(CLAUSE_NUMBER_PATTERN.finditer(text))

    chunks = []
    # enumerate(matches) pairs each item with its index (0, 1, 2, ...) --
    # the same idea as C#'s matches.Select((m, i) => (i, m)), but built in.
    for index, match in enumerate(matches):
        # match.group(1) is the first captured group -- the clause number
        # itself, e.g. "1.1" (the optional trailing "." from the pattern is
        # deliberately outside the capturing group, so it's never included).
        locator = match.group(1)

        # match.end() is the index in `text` immediately after this whole
        # match (number + optional dot + trailing whitespace) -- where this
        # clause's own text starts.
        chunk_start = match.end()
        # This clause's text runs up to wherever the *next* clause number
        # starts (match.start() of the next match), or to the end of the
        # text if this is the last clause.
        chunk_end = matches[index + 1].start() if index + 1 < len(matches) else len(text)

        chunk_text = text[chunk_start:chunk_end].strip()

        # A clause number with no text after it (e.g. two clause markers
        # back-to-back with nothing between them) isn't a real citable unit.
        if chunk_text:
            chunks.append({"locator": locator, "text": chunk_text})

    return chunks


def chunk_document(pdf_path: Path) -> list[dict]:
    # Every strategy module exposes this same chunk_document(pdf_path)
    # shape (see heading_sections.chunk_document for the other one so far),
    # so pipeline.py can call whichever strategy a manifest entry names
    # without needing to know that strategy's own extraction/cleaning
    # needs -- clause_numbered works from plain per-page text, but nothing
    # outside this module has to care.
    raw_pages = extract_pages(pdf_path)
    cleaned_pages = strip_headers_footers_and_page_numbers(raw_pages)
    full_text = "\n".join(cleaned_pages)
    return chunk(full_text)
