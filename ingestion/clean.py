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
#
# Issue #9 first built these two functions with the FSR/DP7 documents'
# *exact* text hardcoded in (a fixed "Réamhrá"/"Global risk assessment" pair,
# a fixed "Annex \d" pattern) -- which meant this file, meant to be a
# reusable pipeline module, only actually worked for two specific Central
# Bank of Ireland documents. Issue #13 generalises both into parameterised
# utilities: the *document-specific* values now live in each manifest
# entry's "cleanup_flags" (each one a {"type": ..., ...params} object,
# where "type" selects the function via CLEANUP_FLAG_TYPES below and
# every other key is passed straight through as that function's keyword
# arguments), while this file only supplies the *mechanism* -- "remove
# everything between two named headings", "remove a line where some pattern
# shows up at least N times" -- which is generic enough to apply to any
# future document with the same *shape* of quirk, not just these two.


def strip_section_between_headings(
    pages: list[list[dict]], start_heading: str, end_heading: str
) -> list[list[dict]]:
    # Removes every line from a heading whose text exactly matches
    # start_heading, up to (but not including) the next heading whose text
    # exactly matches end_heading -- the general shape behind FSR's real
    # "duplicate_section_removal" flag, which sets start_heading="Réamhrá"
    # and end_heading="Global risk assessment" to drop its duplicated
    # Irish-language Preface/Overview. Any other document whose noise is "an
    # unwanted section that starts and ends at two known headings" (a
    # superseded notice, a withdrawn-draft section, ...) can reuse this same
    # function with its own two heading names -- nothing here is specific to
    # FSR's actual headings any more.
    cleaned_pages = []
    # Tracks whether the walk is currently inside the span being removed.
    # Only a heading line whose text is *exactly* one of the two markers
    # toggles this -- every other line, heading or not, is left alone. That
    # matters because some of FSR's own body paragraphs are themselves bold
    # (get_text("dict") marks the whole Réamhrá/Forbhreathnú body as
    # "is_heading", not just the section titles) -- a simpler "any heading
    # line exits the zone" rule would wrongly exit on the very first bold
    # body line of the removed section, instead of at its real end. Keying
    # only off an *exact* text match to the two configured markers avoids
    # that regardless of which document supplies them.
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
    # Removes any line where `pattern` (a regular-expression string) matches
    # at least `minimum_matches` times -- the general shape behind DP7's
    # real "navigation_chrome" flag, which sets pattern="Annex \\d" and
    # minimum_matches=4 to catch its Annex-page nav-breadcrumb footer (e.g.
    # "Annex 1 page 1 of 3 >  | Annex 2  | Annex 3  | Annex 4"): the
    # "page X of Y" part changes on every occurrence, so unlike a running
    # header/footer the line never repeats verbatim and evades the
    # automatic rule above. Any other document whose chrome has the same
    # shape -- some marker mentioned several times on one line, in a way
    # real prose won't plausibly produce -- can reuse this with its own
    # pattern and threshold; nothing here is specific to DP7's Annexes any
    # more.
    #
    # re.compile(...) happens on every call here, unlike the module-level
    # PAGE_NUMBER_PATTERN above -- that constant pattern never changes, so
    # compiling it once at import time is free; `pattern` here is a string
    # supplied per-flag from the manifest, so there's nothing to precompile
    # ahead of time.
    compiled_pattern = re.compile(pattern, re.IGNORECASE)
    return [
        [
            line
            for line in page_lines
            if len(compiled_pattern.findall(line["text"])) < minimum_matches
        ]
        for page_lines in pages
    ]


# A dict from a manifest cleanup flag's "type" to the function that
# implements it -- the same lookup-table-of-functions idea pipeline.py uses
# for CHUNKING_STRATEGIES, so a new flag type only needs registering here,
# never a change to whichever strategy module applies it.
CLEANUP_FLAG_TYPES = {
    "duplicate_section_removal": strip_section_between_headings,
    "navigation_chrome": strip_lines_with_repeated_pattern,
}


def apply_cleanup_flags(pages: list[list[dict]], flags: list[dict]) -> list[list[dict]]:
    # Each flag is a manifest-supplied object like
    # {"type": "navigation_chrome", "pattern": "Annex \\d", "minimum_matches": 4}
    # -- "type" selects the function via CLEANUP_FLAG_TYPES, and every other
    # key is passed straight through as that function's keyword arguments
    # (dict(flag) copies the flag first so .pop("type") below doesn't mutate
    # the manifest entry the caller passed in). If a flag's remaining keys
    # don't match its function's parameter names -- a typo'd manifest field,
    # e.g. "min_matches" instead of "minimum_matches" -- Python's own
    # keyword-argument matching raises a TypeError for us; nothing extra to
    # write for that.
    for flag in flags:
        flag = dict(flag)
        # CLEANUP_FLAG_TYPES[...] deliberately uses [], not .get(...) -- an
        # unrecognised flag type (a typo in the manifest, most likely)
        # should raise loudly rather than silently doing nothing, the same
        # reasoning pipeline.py already applies to an unrecognised
        # chunking_strategy.
        cleanup_function = CLEANUP_FLAG_TYPES[flag.pop("type")]
        pages = cleanup_function(pages, **flag)
    return pages
