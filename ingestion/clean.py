# Automatic text cleanup (ADR-0016): stripping repeated headers/footers and
# bare page-number lines. This is deliberately the *only* cleanup this
# pipeline does without a human declaring it in the manifest -- both rules
# here are safe, mechanical pattern-matches with no real judgment call
# involved, unlike document-specific quirks (bilingual duplication,
# navigation chrome), which stay manifest-flagged (a later ticket).

from collections import Counter


def strip_headers_footers_and_page_numbers(pages: list[str]) -> list[str]:
    # "list[str]" as a type hint means "a list of strings" -- Python's
    # built-in generic syntax, equivalent to C#'s List<string>. As with all
    # type hints here, it's documentation only; nothing enforces it at
    # runtime.

    # .split("\n") breaks each page's raw text into one string per line
    # (pymupdf's get_text() already uses "\n" as the line separator). This
    # gives a list of lists: one inner list of lines per page.
    pages_as_lines = [page.split("\n") for page in pages]

    # .strip() removes leading/trailing whitespace from a string -- the
    # same idea as C#'s string.Trim(). We compare *normalized* lines
    # (whitespace-trimmed) so that e.g. "CP 54 " and "CP 54" still count as
    # the same repeated line, without permanently discarding the original
    # spacing from lines we decide to keep.
    normalized_pages = [
        [line.strip() for line in lines] for lines in pages_as_lines
    ]

    # Counter is a dict subclass from Python's standard library that counts
    # how many times each value occurs -- roughly a shortcut for what you'd
    # build by hand with a Dictionary<string, int> and a foreach loop that
    # increments a count per key.
    #
    # For each page we count each *distinct* non-blank line once (via set(...)
    # before updating the counter), not once per occurrence on that page --
    # otherwise a line repeated twice on the same page (e.g. by accident in
    # a table) would inflate its count and look like it repeats across more
    # pages than it actually does.
    line_counts: Counter[str] = Counter()
    for lines in normalized_pages:
        distinct_non_blank_lines = {line for line in lines if line}
        line_counts.update(distinct_non_blank_lines)

    number_of_pages = len(pages)
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
    repeated_often_enough_to_be_boilerplate = {
        line for line, count in line_counts.items() if count >= header_footer_threshold
    }

    cleaned_pages = []
    for lines in normalized_pages:
        kept_lines = [
            line
            for line in lines
            # Blank lines carry nothing to keep either way.
            if line
            # A line that repeats often enough is a header/footer.
            and line not in repeated_often_enough_to_be_boilerplate
            # str.isdigit() is true only when every character is a digit --
            # comparable to a regex like ^\d+$, or C#'s
            # line.All(char.IsDigit). A line that's nothing but digits is a
            # page number, not real content.
            and not line.isdigit()
        ]
        cleaned_pages.append("\n".join(kept_lines))

    return cleaned_pages
