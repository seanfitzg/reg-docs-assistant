# Automatic text cleanup (ADR-0016): stripping repeated headers/footers and
# page-number lines. This is deliberately the *only* cleanup this pipeline
# does without a human declaring it in the manifest -- both rules here are
# safe, mechanical pattern-matches with no real judgment call involved,
# unlike document-specific quirks (bilingual duplication, navigation
# chrome), which stay manifest-flagged (a later ticket).
#
# Two public functions share the same underlying rules but work on
# different shapes: strip_headers_footers_and_page_numbers() takes plain
# per-page text (what extract_pages() returns, used by clause_numbered);
# strip_headers_footers_and_page_numbers_from_layout() takes the
# list[list[dict]] shape extract_pages_with_headings() returns, and
# preserves each surviving line's "is_heading" flag alongside it (needed by
# heading_sections, which extract_pages() throws away by design).

import re
from collections import Counter

# re.compile(...) pre-builds this pattern once rather than re-parsing it on
# every call -- the same idea as a static readonly Regex field in C#.
# fullmatch (used below, not search/match) requires the *entire* line to
# match, not just some substring within it.
#   (?:page\s+)?   an optional, non-capturing "page " (or "Page ", "PAGE ",
#                  ... -- see re.IGNORECASE below) prefix
#   \d+            one or more digits
# This intentionally only matches a line that is *nothing but* an optional
# "page" word and a number -- "Page 5" or "5", never "Page 5 of the
# Handbook" or a sentence that happens to contain a number.
PAGE_NUMBER_PATTERN = re.compile(r"(?:page\s+)?\d+", re.IGNORECASE)


def _is_page_number(line: str) -> bool:
    return bool(PAGE_NUMBER_PATTERN.fullmatch(line))


def _find_boilerplate_lines(pages_of_lines: list[list[str]]) -> set[str]:
    # This is the shared core both public functions below call: given each
    # page's lines (already whitespace-trimmed), work out which distinct
    # lines of text count as a running header/footer.

    # Counter is a dict subclass from Python's standard library that counts
    # how many times each value occurs -- roughly a shortcut for what you'd
    # build by hand with a Dictionary<string, int> and a foreach loop that
    # increments a count per key.
    #
    # For each page we count each *distinct* non-blank line once (via
    # set(...) before updating the counter), not once per occurrence on
    # that page -- otherwise a line repeated twice on the same page (e.g.
    # by accident in a table) would inflate its count and look like it
    # repeats across more pages than it actually does.
    line_counts: Counter[str] = Counter()
    for lines in pages_of_lines:
        distinct_non_blank_lines = {line for line in lines if line}
        line_counts.update(distinct_non_blank_lines)

    number_of_pages = len(pages_of_lines)
    # A line counts as a running header/footer once it repeats verbatim on
    # at least 3 pages -- or, for a document shorter than 3 pages, on all
    # of them (there's no "3 pages" to require from a 1- or 2-page
    # document). This started life as "every single page" and then
    # "a majority of pages", but inspecting the real CP54 PDF while
    # building this pipeline showed neither survives contact with a real
    # document: its running header prints on only 15 of its 96 pages (the
    # discussion section; the other 81 are the appended draft Code text
    # with a different header), which is neither "every page" nor
    # "a majority". A small absolute count still keeps the same safety
    # property "every page" was chosen for in the first place -- real prose
    # essentially never repeats itself verbatim three separate times,
    # anywhere in a document, regardless of how long that document is.
    header_footer_threshold = min(3, number_of_pages)
    return {
        line for line, count in line_counts.items() if count >= header_footer_threshold
    }


def strip_headers_footers_and_page_numbers(pages: list[str]) -> list[str]:
    # .split("\n") breaks each page's raw text into one string per line
    # (pymupdf's get_text() already uses "\n" as the line separator). This
    # gives a list of lists: one inner list of lines per page.
    #
    # .strip() removes leading/trailing whitespace from a string -- the
    # same idea as C#'s string.Trim(). We compare *normalized* lines
    # (whitespace-trimmed) so that e.g. "CP 54 " and "CP 54" still count as
    # the same repeated line, without permanently discarding the original
    # spacing from lines we decide to keep.
    normalized_pages = [
        [line.strip() for line in page.split("\n")] for page in pages
    ]

    boilerplate_lines = _find_boilerplate_lines(normalized_pages)

    cleaned_pages = []
    for lines in normalized_pages:
        kept_lines = [
            line
            for line in lines
            # Blank lines carry nothing to keep either way.
            if line
            # A line that repeats often enough is a header/footer.
            and line not in boilerplate_lines
            # A line that's just an optional "page" word plus a number
            # (e.g. "5", "Page 5") is a page number, not real content.
            and not _is_page_number(line)
        ]
        cleaned_pages.append("\n".join(kept_lines))

    return cleaned_pages


def strip_headers_footers_and_page_numbers_from_layout(
    pages: list[list[dict]],
) -> list[list[dict]]:
    normalized_pages = [
        [line["text"].strip() for line in page_lines] for page_lines in pages
    ]

    boilerplate_lines = _find_boilerplate_lines(normalized_pages)

    cleaned_pages = []
    for page_lines in pages:
        kept_lines = []
        for line in page_lines:
            normalized_text = line["text"].strip()
            if (
                normalized_text
                and normalized_text not in boilerplate_lines
                and not _is_page_number(normalized_text)
            ):
                # Rebuild the dict with the *normalized* text (matching what
                # strip_headers_footers_and_page_numbers keeps above), but
                # carry the original "is_heading" flag through untouched --
                # that flag is the entire reason this variant exists.
                kept_lines.append({"text": normalized_text, "is_heading": line["is_heading"]})
        cleaned_pages.append(kept_lines)

    return cleaned_pages
