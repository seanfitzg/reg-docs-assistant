# Automatic text cleanup (ADR-0016): stripping repeated headers/footers and
# page-number lines. This is deliberately the *only* cleanup applied without
# a human declaring it in the manifest -- both rules here are safe,
# mechanical pattern-matches with no real judgment call involved. Further
# down, the "Manifest-flagged cleanup" section covers the opposite case:
# document-specific quirks (bilingual duplication, navigation chrome) that
# only apply when a manifest entry names them explicitly (issue #9).
#
# Two public functions share the same underlying automatic rules but work
# on different shapes: strip_headers_footers_and_page_numbers() takes plain
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


def _keep_line(normalized_text: str, boilerplate_lines: set[str]) -> bool:
    # Shared by both public functions below, so the actual keep/discard
    # rule is written -- and explained -- exactly once, however many
    # different input shapes end up calling it.
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
        kept_lines = [line for line in lines if _keep_line(line, boilerplate_lines)]
        cleaned_pages.append("\n".join(kept_lines))

    return cleaned_pages


def strip_headers_footers_and_page_numbers_from_layout(
    pages: list[list[dict]],
) -> list[list[dict]]:
    # This variant takes the shape extract_pages_with_headings() produces:
    # one list per page, each item a dict {"text": str, "is_heading": bool}
    # for one line -- not a plain string per page, the way extract_pages()
    # (and the function above) works. line["text"]/line["is_heading"] is a
    # dict lookup by key, the same as C#'s dict["key"] indexer; it's safe
    # here (no KeyError risk) because every dict in this shape always has
    # both keys, guaranteed by whichever function built it.
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
                # Rebuild the dict with the *normalized* text (matching what
                # strip_headers_footers_and_page_numbers keeps above), but
                # carry the original "is_heading" flag through untouched --
                # that flag is the entire reason this variant exists.
                kept_lines.append({"text": normalized_text, "is_heading": line["is_heading"]})
        cleaned_pages.append(kept_lines)

    return cleaned_pages


# ---- Manifest-flagged cleanup (ADR-0016) ----
#
# Everything above is safe and automatic because it's mechanical, with no
# real judgment call. What follows is the opposite: document-specific noise
# that only a human reading the document would recognise as noise, so it's
# never applied automatically -- only when a manifest entry names it
# explicitly via "cleanup_flags" (pipeline.py passes that list straight
# through to apply_cleanup_flags() below). Both functions here work on the
# same list[list[dict]] layout shape as the _from_layout variant above,
# since both documents these were built for (issue #9) use heading_sections.

# The Financial Stability Review prints its Preface/Overview a second time
# in Irish immediately afterwards -- "Réamhrá"/"Forbhreathnú" are the Irish
# for "Preface"/"Overview" -- before the document's real content resumes at
# "Global risk assessment" (confirmed by directly inspecting the real PDF
# while building this). This can't be caught by the automatic rule above:
# it's a *translation*, different text expressing the same content, not a
# verbatim-repeated line.
BILINGUAL_DUPLICATE_SECTION_START = "Réamhrá"
BILINGUAL_DUPLICATE_SECTION_END = "Global risk assessment"


def strip_bilingual_duplicate_content(pages: list[list[dict]]) -> list[list[dict]]:
    cleaned_pages = []
    # Tracks whether the walk is currently inside the Irish-language
    # duplicate span. Only a heading line whose text is *exactly* one of the
    # two markers above toggles this -- every other line, heading or not, is
    # left alone. That matters because some of this document's body
    # paragraphs are themselves bold (get_text("dict") marks the whole
    # Réamhrá/Forbhreathnú body as "is_heading", not just the section
    # titles) -- a simpler "any heading line exits the zone" rule would
    # wrongly exit on the very first bold body line of the Irish section,
    # instead of at its real end.
    in_duplicate_section = False
    for page_lines in pages:
        kept_lines = []
        for line in page_lines:
            if line["is_heading"] and line["text"] == BILINGUAL_DUPLICATE_SECTION_START:
                in_duplicate_section = True
            elif line["is_heading"] and line["text"] == BILINGUAL_DUPLICATE_SECTION_END:
                in_duplicate_section = False
            if not in_duplicate_section:
                kept_lines.append(line)
        cleaned_pages.append(kept_lines)
    return cleaned_pages


# DP7's Annex pages carry a nav-breadcrumb footer naming all four Annexes so
# a reader can jump between them, e.g. "Annex 1 page 1 of 3 >  | Annex 2  |
# Annex 3  | Annex 4" -- but because the "page X of Y" part changes on every
# occurrence, the line never repeats verbatim, so it evades the automatic
# rule above the same way a running "Page N" footer did before that got its
# own rule. A line naming all four Annexes is specific enough to this
# document's chrome that real prose won't plausibly produce a false
# positive.
ANNEX_MENTION_PATTERN = re.compile(r"Annex \d", re.IGNORECASE)
NAVIGATION_CHROME_ANNEX_MENTIONS_THRESHOLD = 4


def _is_navigation_chrome(text: str) -> bool:
    return len(ANNEX_MENTION_PATTERN.findall(text)) >= NAVIGATION_CHROME_ANNEX_MENTIONS_THRESHOLD


def strip_navigation_chrome(pages: list[list[dict]]) -> list[list[dict]]:
    return [
        [line for line in page_lines if not _is_navigation_chrome(line["text"])]
        for page_lines in pages
    ]


# A dict from a manifest's "cleanup_flags" entry (a string) to the function
# that implements it -- the same lookup-table-of-functions idea pipeline.py
# uses for CHUNKING_STRATEGIES, so a new flag only needs registering here,
# never a change to whichever strategy module applies it.
CLEANUP_FLAGS = {
    "bilingual_duplicate_content": strip_bilingual_duplicate_content,
    "navigation_chrome": strip_navigation_chrome,
}


def apply_cleanup_flags(pages: list[list[dict]], flags: list[str]) -> list[list[dict]]:
    # CLEANUP_FLAGS[flag] deliberately uses [], not .get(...) -- an
    # unrecognised flag name (a typo in the manifest, most likely) should
    # raise loudly rather than silently doing nothing, the same reasoning
    # pipeline.py already applies to an unrecognised chunking_strategy.
    for flag in flags:
        pages = CLEANUP_FLAGS[flag](pages)
    return pages
