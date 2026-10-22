# Automatic text cleanup (ADR-0016): stripping repeated headers/footers and
# page-number lines. This is deliberately the only cleanup applied without a
# human declaring it in the manifest -- both rules are safe, mechanical
# pattern-matches. The "Manifest-flagged cleanup" section below covers
# document-specific quirks (bilingual duplication, navigation chrome) that
# apply only when a manifest entry names them (issue #9).
#
# Two public functions share the same automatic rules but work on different
# shapes: strip_headers_footers_and_page_numbers() takes plain per-page text
# (extract_pages(), used by clause_numbered);
# strip_headers_footers_and_page_numbers_from_layout() takes the
# list[list[dict]] shape of extract_pages_with_headings() and preserves each
# line's "is_heading" flag (needed by heading_sections).

import re
from collections import Counter

# fullmatch (below) requires the *entire* line to match, so this only matches
# a line that is nothing but an optional "page" word and a number ("Page 5",
# "5"), never "Page 5 of the Handbook" or a sentence containing a number.
PAGE_NUMBER_PATTERN = re.compile(r"(?:page\s+)?\d+", re.IGNORECASE)


def _is_page_number(line: str) -> bool:
    return bool(PAGE_NUMBER_PATTERN.fullmatch(line))


def _find_boilerplate_lines(pages_of_lines: list[list[str]]) -> set[str]:
    # Shared core of both public functions: given each page's
    # whitespace-trimmed lines, find the distinct lines that count as a
    # running header/footer.

    # Each distinct non-blank line is counted once per page (via the set), so
    # a line repeated twice on one page (e.g. by accident in a table) doesn't
    # look like it repeats across more pages than it does.
    line_counts: Counter[str] = Counter()
    for lines in pages_of_lines:
        distinct_non_blank_lines = {line for line in lines if line}
        line_counts.update(distinct_non_blank_lines)

    number_of_pages = len(pages_of_lines)
    # A line is a running header/footer once it repeats verbatim on at least 3
    # pages -- or on all of them, for a document shorter than 3 pages. This
    # started as "every page", then "a majority of pages", but the real CP54
    # PDF showed neither works: its running header prints on only 15 of 96
    # pages (the other 81 are appended draft Code text with a different
    # header). A small absolute count keeps the safety property "every page"
    # was chosen for: real prose essentially never repeats verbatim three
    # times, however long the document.
    header_footer_threshold = min(3, number_of_pages)
    return {
        line for line, count in line_counts.items() if count >= header_footer_threshold
    }


def _keep_line(normalized_text: str, boilerplate_lines: set[str]) -> bool:
    # The single keep/discard rule shared by both public functions.
    return (
        # A blank line carries nothing to keep either way.
        bool(normalized_text)
        # A line that repeats often enough is a header/footer.
        and normalized_text not in boilerplate_lines
        # A line that's just an optional "page" word plus a number
        # (e.g. "5", "Page 5") is a page number, not real content.
        and not _is_page_number(normalized_text)
    )


def strip_headers_footers_and_page_numbers(pages: list[str]) -> list[str]:
    # Compare *normalized* (trimmed) lines so "CP 54 " and "CP 54" count as
    # the same repeated line, without discarding the original spacing of lines
    # we keep.
    normalized_pages = [[line.strip() for line in page.split("\n")] for page in pages]

    boilerplate_lines = _find_boilerplate_lines(normalized_pages)

    cleaned_pages = []
    for lines in normalized_pages:
        kept_lines = [line for line in lines if _keep_line(line, boilerplate_lines)]
        cleaned_pages.append("\n".join(kept_lines))

    return cleaned_pages


def strip_headers_footers_and_page_numbers_from_layout(
    pages: list[list[dict]],
) -> list[list[dict]]:
    # Takes extract_pages_with_headings()'s shape: per page, a list of
    # {"text": str, "is_heading": bool} dicts, one per line.
    normalized_pages = [
        [line["text"].strip() for line in page_lines] for page_lines in pages
    ]

    boilerplate_lines = _find_boilerplate_lines(normalized_pages)

    cleaned_pages = []
    for page_lines in pages:
        kept_lines = []
        for line in page_lines:
            normalized_text = line["text"].strip()
            if _keep_line(normalized_text, boilerplate_lines):
                # Keep the normalized text (as the plain-text variant does)
                # and carry "is_heading" through -- the reason this variant
                # exists.
                kept_lines.append(
                    {"text": normalized_text, "is_heading": line["is_heading"]}
                )
        cleaned_pages.append(kept_lines)

    return cleaned_pages


# ---- Manifest-flagged cleanup (ADR-0016) ----
#
# Everything above is automatic because it's mechanical. What follows is
# document-specific noise only a human would recognise, so it's applied only
# when a manifest entry names it in "cleanup_flags" (pipeline.py passes that
# list to apply_cleanup_flags()). Both functions work on the same
# list[list[dict]] layout shape as the _from_layout variant, since both
# documents they were built for (issue #9) use heading_sections.
#
# Issue #9 hardcoded the FSR/DP7 documents' exact text here. Issue #13
# generalised it: document-specific values now live in each manifest entry's
# "cleanup_flags" ({"type": ..., ...params}, where "type" selects the function
# via CLEANUP_FLAG_TYPES and the other keys are its keyword arguments), and
# this file supplies only the generic mechanism -- "remove everything between
# two named headings", "remove a line where a pattern appears at least N
# times".


def strip_section_between_headings(
    pages: list[list[dict]], start_heading: str, end_heading: str
) -> list[list[dict]]:
    # Removes every line from a heading whose text exactly matches
    # start_heading, up to (but not including) the next heading exactly
    # matching end_heading. FSR's "duplicate_section_removal" flag uses it
    # with "Réamhrá" and "Global risk assessment" to drop its duplicated
    # Irish-language Preface/Overview; any "unwanted section between two known
    # headings" can reuse it.
    cleaned_pages = []
    # Only a heading with text *exactly* equal to a marker toggles this. A
    # simpler "any heading exits the zone" rule would exit too early, because
    # some of FSR's body paragraphs are bold too (get_text("dict") marks the
    # whole Réamhrá/Forbhreathnú body as "is_heading").
    in_removed_section = False
    for page_lines in pages:
        kept_lines = []
        for line in page_lines:
            if line["is_heading"] and line["text"] == start_heading:
                in_removed_section = True
            elif line["is_heading"] and line["text"] == end_heading:
                in_removed_section = False
            if not in_removed_section:
                kept_lines.append(line)
        cleaned_pages.append(kept_lines)
    return cleaned_pages


def strip_lines_with_repeated_pattern(
    pages: list[list[dict]], pattern: str, minimum_matches: int
) -> list[list[dict]]:
    # Removes any line where the regex `pattern` matches at least
    # `minimum_matches` times. DP7's "navigation_chrome" flag uses it with
    # pattern="Annex \\d" and minimum_matches=4 to catch its Annex-page
    # breadcrumb footer (e.g. "Annex 1 page 1 of 3 >  | Annex 2  | Annex 3  |
    # Annex 4"). The "page X of Y" part changes each time, so the line never
    # repeats verbatim and evades the automatic header/footer rule. Any
    # chrome with a marker repeated on one line, in a way prose won't
    # plausibly produce, can reuse it.
    #
    # Compiled per call (unlike PAGE_NUMBER_PATTERN) because the pattern is
    # supplied per-flag from the manifest.
    compiled_pattern = re.compile(pattern, re.IGNORECASE)
    return [
        [
            line
            for line in page_lines
            if len(compiled_pattern.findall(line["text"])) < minimum_matches
        ]
        for page_lines in pages
    ]


# Maps a manifest cleanup flag's "type" to its function, like pipeline.py's
# CHUNKING_STRATEGIES: a new flag type is registered here only.
CLEANUP_FLAG_TYPES = {
    "duplicate_section_removal": strip_section_between_headings,
    "navigation_chrome": strip_lines_with_repeated_pattern,
}


def apply_cleanup_flags(pages: list[list[dict]], flags: list[dict]) -> list[list[dict]]:
    # Each flag is a manifest object like
    # {"type": "navigation_chrome", "pattern": "Annex \\d", "minimum_matches": 4}:
    # "type" selects the function and the other keys are passed as its keyword
    # arguments. The flag is copied first so pop("type") doesn't mutate the
    # caller's manifest entry. A typo'd key (e.g. "min_matches") raises a
    # TypeError from Python's keyword matching.
    for flag in flags:
        flag = dict(flag)
        # [] not .get(): an unrecognised flag type (likely a manifest typo)
        # should fail loudly, as pipeline.py does for an unrecognised
        # chunking_strategy.
        cleanup_function = CLEANUP_FLAG_TYPES[flag.pop("type")]
        pages = cleanup_function(pages, **flag)
    return pages
