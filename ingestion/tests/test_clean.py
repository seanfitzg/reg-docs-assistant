# Tests for clean.py: the automatic (no manifest flag needed) cleanup step
# from ADR-0016 -- stripping running headers/footers, plus the closely
# related case of bare page-number lines, which don't repeat verbatim (the
# number itself changes every page) but are just as mechanical and
# judgment-free to detect and remove.

from clean import strip_headers_footers_and_page_numbers


def test_line_repeated_on_every_page_is_stripped():
    pages = [
        "Consultation Paper CP 54\nFirst page content.",
        "Consultation Paper CP 54\nSecond page content.",
        "Consultation Paper CP 54\nThird page content.",
    ]

    cleaned = strip_headers_footers_and_page_numbers(pages)

    assert "Consultation Paper CP 54" not in cleaned[0]
    assert "Consultation Paper CP 54" not in cleaned[1]
    assert "Consultation Paper CP 54" not in cleaned[2]


def test_real_content_on_every_page_is_kept():
    pages = [
        "Consultation Paper CP 54\nFirst page content.",
        "Consultation Paper CP 54\nSecond page content.",
        "Consultation Paper CP 54\nThird page content.",
    ]

    cleaned = strip_headers_footers_and_page_numbers(pages)

    assert "First page content." in cleaned[0]
    assert "Second page content." in cleaned[1]
    assert "Third page content." in cleaned[2]


def test_line_repeated_on_only_a_small_fraction_of_a_long_document_is_still_stripped():
    # Real documents can confine one header style to a single section, not
    # the whole document -- inspecting the actual CP54 PDF while building
    # this pipeline found its running header printed on only 15 of its 96
    # pages (the discussion section; the rest is the appended draft Code
    # text under a different header). Neither "every page" nor "a majority
    # of pages" would ever fire there. What both this real case and this
    # synthetic one share is a line repeating far more often than real
    # prose plausibly would: here, 5 of 20 pages.
    #
    # "X if cond else Y" is Python's conditional expression (the equivalent
    # of C#'s "cond ? X : Y" ternary), used here *inside* a list
    # comprehension -- for each i in range(20), it evaluates the ternary to
    # decide which string that page gets, producing a 20-item list in one
    # expression rather than a separate loop with an if/else inside it.
    pages = ["Running Header\nReal page content." if i < 5 else f"Page {i} unique content." for i in range(20)]

    cleaned = strip_headers_footers_and_page_numbers(pages)

    for page_text in cleaned[:5]:
        assert "Running Header" not in page_text


def test_line_only_on_one_page_is_not_treated_as_a_header():
    # A line has to repeat across *every* page to count as a header/footer
    # -- ADR-0016 chose this mechanical, no-judgment-call rule specifically
    # because it has no real false-positive risk. A line that only shows up
    # once is exactly the kind of thing that rule must never touch.
    pages = [
        "1.1\nPurpose",
        "1.2\nScope",
    ]

    cleaned = strip_headers_footers_and_page_numbers(pages)

    assert "Purpose" in cleaned[0]
    assert "Scope" in cleaned[1]


def test_bare_page_number_lines_are_stripped():
    # Page numbers ascend every page, so they never repeat verbatim -- they
    # need their own rule: a line that is *only* digits is a page number,
    # not real content, on essentially any document.
    pages = [
        "6\nSome real text on page six.",
        "7\nSome real text on page seven.",
    ]

    cleaned = strip_headers_footers_and_page_numbers(pages)

    assert "6" not in cleaned[0].splitlines()
    assert "7" not in cleaned[1].splitlines()
    assert "Some real text on page six." in cleaned[0]
    assert "Some real text on page seven." in cleaned[1]


def test_a_number_that_is_part_of_real_text_is_kept():
    # Only a line that is *nothing but* digits is treated as a page number.
    # A line like "1.1" (a clause locator) or a sentence containing a number
    # must survive untouched.
    pages = ["1.1\nThe fee is 30 days.", "1.2\nMore text."]

    cleaned = strip_headers_footers_and_page_numbers(pages)

    assert "1.1" in cleaned[0]
    assert "The fee is 30 days." in cleaned[0]
