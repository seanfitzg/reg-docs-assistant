# Tests for clean.py: the automatic (no manifest flag needed) cleanup step
# from ADR-0016 -- stripping running headers/footers, plus the closely
# related case of bare page-number lines, which don't repeat verbatim (the
# number itself changes every page) but are just as mechanical and
# judgment-free to detect and remove.

import pytest

from clean import (
    apply_cleanup_flags,
    strip_bilingual_duplicate_content,
    strip_headers_footers_and_page_numbers,
    strip_headers_footers_and_page_numbers_from_layout,
    strip_navigation_chrome,
)


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


def test_page_prefixed_page_number_lines_are_stripped():
    # DP8's real running footer is "Page 5", "Page 6", ... -- a page number
    # with a "Page " prefix, which is neither a repeated verbatim line
    # (the digit changes every page) nor caught by the bare-digit rule
    # above (the line isn't *only* digits). It needs its own recognition,
    # same mechanical justification as bare digits: no real sentence is
    # ever just the word "Page" followed by a number and nothing else.
    pages = ["Page 5\nReal text on page five.", "Page 6\nReal text on page six."]

    cleaned = strip_headers_footers_and_page_numbers(pages)

    assert "Page 5" not in cleaned[0].splitlines()
    assert "Page 6" not in cleaned[1].splitlines()
    assert "Real text on page five." in cleaned[0]


def test_a_number_that_is_part_of_real_text_is_kept():
    # Only a line that is *nothing but* digits is treated as a page number.
    # A line like "1.1" (a clause locator) or a sentence containing a number
    # must survive untouched.
    pages = ["1.1\nThe fee is 30 days.", "1.2\nMore text."]

    cleaned = strip_headers_footers_and_page_numbers(pages)

    assert "1.1" in cleaned[0]
    assert "The fee is 30 days." in cleaned[0]


# ---- Layout-aware variant, for heading_sections documents ----
#
# heading_sections needs to know *which* surviving lines are headings
# (extract_pages_with_headings' "is_heading" flag), not just their text --
# so this variant works on the structured list[list[dict]] shape instead of
# plain per-page strings, but applies the exact same boilerplate rules.

def test_layout_variant_strips_repeated_lines_but_keeps_the_heading_flag():
    pages = [
        [
            {"text": "Central Bank of Ireland", "is_heading": False},
            {"text": "Purpose", "is_heading": True},
            {"text": "Real content here.", "is_heading": False},
        ],
        [
            {"text": "Central Bank of Ireland", "is_heading": False},
            {"text": "Background", "is_heading": True},
            {"text": "More real content.", "is_heading": False},
        ],
        [
            {"text": "Central Bank of Ireland", "is_heading": False},
            {"text": "Governance", "is_heading": True},
            {"text": "Even more content.", "is_heading": False},
        ],
    ]

    cleaned = strip_headers_footers_and_page_numbers_from_layout(pages)

    # The repeated header line is gone from every page...
    for page_lines in cleaned:
        assert all(line["text"] != "Central Bank of Ireland" for line in page_lines)

    # ...but the real lines, and whether each one is a heading, survive.
    assert cleaned[0] == [
        {"text": "Purpose", "is_heading": True},
        {"text": "Real content here.", "is_heading": False},
    ]


def test_layout_variant_strips_page_number_lines():
    # Distinct content per page here, deliberately -- identical content on
    # both pages would itself trigger the header/footer rule and confuse
    # what this test is actually checking.
    pages = [
        [{"text": "Page 5", "is_heading": False}, {"text": "Content on five.", "is_heading": False}],
        [{"text": "Page 6", "is_heading": False}, {"text": "Content on six.", "is_heading": False}],
    ]

    cleaned = strip_headers_footers_and_page_numbers_from_layout(pages)

    assert cleaned[0] == [{"text": "Content on five.", "is_heading": False}]


# ---- Manifest-flagged cleanup (ADR-0016) ----
#
# Unlike the automatic rules above, these only ever run when a manifest
# entry names them explicitly (issue #9) -- so every test here builds its
# own small fixture rather than relying on anything being auto-detected.

def test_bilingual_duplicate_content_is_removed_between_start_and_end_markers():
    # Mirrors the real FSR document's shape: an English "Preface" section,
    # then the Irish-language "Réamhrá" duplicate, then real content resumes
    # at "Global risk assessment". Only the middle section should go.
    pages = [
        [
            {"text": "Preface", "is_heading": True},
            {"text": "English preface content.", "is_heading": False},
        ],
        [
            {"text": "Réamhrá", "is_heading": True},
            {"text": "Irish duplicate content.", "is_heading": False},
        ],
        [
            {"text": "Global risk assessment", "is_heading": True},
            {"text": "Real content resumes here.", "is_heading": False},
        ],
    ]

    cleaned = strip_bilingual_duplicate_content(pages)

    assert cleaned[0] == [
        {"text": "Preface", "is_heading": True},
        {"text": "English preface content.", "is_heading": False},
    ]
    assert cleaned[1] == []
    assert cleaned[2] == [
        {"text": "Global risk assessment", "is_heading": True},
        {"text": "Real content resumes here.", "is_heading": False},
    ]


def test_bilingual_duplicate_content_spanning_multiple_pages_is_removed():
    # The real FSR document's Irish section runs across several pages
    # (Réamhrá on one page, Forbhreathnú starting on the next, with its own
    # content continuing onto a third) before "Global risk assessment"
    # finally appears -- the removal has to survive page boundaries, not
    # just work within a single page.
    pages = [
        [{"text": "Réamhrá", "is_heading": True}, {"text": "Irish page one.", "is_heading": False}],
        [{"text": "Forbhreathnú", "is_heading": True}, {"text": "Irish page two.", "is_heading": False}],
        [{"text": "Irish page three, no heading here.", "is_heading": False}],
        [{"text": "Global risk assessment", "is_heading": True}, {"text": "Real content.", "is_heading": False}],
    ]

    cleaned = strip_bilingual_duplicate_content(pages)

    assert cleaned[0] == []
    assert cleaned[1] == []
    assert cleaned[2] == []
    assert cleaned[3] == [
        {"text": "Global risk assessment", "is_heading": True},
        {"text": "Real content.", "is_heading": False},
    ]


def test_bold_body_line_inside_duplicate_section_does_not_end_it_early():
    # The real Réamhrá/Forbhreathnú sections in FSR come out of
    # extract_pages_with_headings with their *entire* body marked
    # is_heading=True, not just the section title -- pymupdf reports that
    # text as bold, and extract_pages_with_headings has no way to tell "a
    # real heading" from "a bold paragraph" apart (heading_sections.py's own
    # module comment documents this same ambiguity for a different case). A
    # naive "any heading line exits the zone" rule would wrongly stop
    # removing right after the section title, keeping everything else in
    # the section. This line's text isn't the end marker, so it must not
    # end the zone.
    pages = [
        [
            {"text": "Réamhrá", "is_heading": True},
            {"text": "This whole line is bold too, but isn't the end marker.", "is_heading": True},
            {"text": "Global risk assessment", "is_heading": True},
            {"text": "Real content.", "is_heading": False},
        ],
    ]

    cleaned = strip_bilingual_duplicate_content(pages)

    assert cleaned[0] == [
        {"text": "Global risk assessment", "is_heading": True},
        {"text": "Real content.", "is_heading": False},
    ]


def test_content_with_no_bilingual_markers_is_unaffected():
    pages = [
        [{"text": "Purpose", "is_heading": True}, {"text": "Ordinary content.", "is_heading": False}],
    ]

    cleaned = strip_bilingual_duplicate_content(pages)

    assert cleaned == pages


def test_navigation_chrome_line_naming_all_four_annexes_is_stripped():
    # Modelled on DP7's real Annex nav-breadcrumb footer, e.g.
    # "Annex 1 page 1 of 3 >  | Annex 2  | Annex 3  | Annex 4" -- the
    # "page X of Y" part changes every occurrence, so unlike a running
    # header/footer this line never repeats verbatim (ADR-0016) and needs
    # its own rule.
    pages = [
        [
            {"text": "Annex 1 page 1 of 3 >  | Annex 2  | Annex 3  | Annex 4", "is_heading": True},
            {"text": "Real annex content.", "is_heading": False},
        ],
    ]

    cleaned = strip_navigation_chrome(pages)

    assert cleaned[0] == [{"text": "Real annex content.", "is_heading": False}]


def test_navigation_chrome_line_naming_fewer_than_four_annexes_is_kept():
    # DP7's real Table of Contents lists "Annex 1", "Annex 2", "Annex 3" and
    # "Annex 4" as four *separate* lines, each naming only one Annex -- real
    # content, not the nav footer, and must survive. A sentence that
    # legitimately references one Annex (e.g. "in Annex 2.") must too.
    pages = [
        [
            {"text": "Annex 1", "is_heading": False},
            {"text": "Annex 2", "is_heading": False},
            {"text": "See the detail in Annex 2.", "is_heading": False},
        ],
    ]

    cleaned = strip_navigation_chrome(pages)

    assert cleaned == pages


def test_apply_cleanup_flags_runs_the_named_flag():
    pages = [
        [{"text": "Annex 1 >  | Annex 2  | Annex 3  | Annex 4", "is_heading": False}],
    ]

    cleaned = apply_cleanup_flags(pages, ["navigation_chrome"])

    assert cleaned[0] == []


def test_apply_cleanup_flags_with_no_flags_is_a_no_op():
    pages = [[{"text": "Untouched.", "is_heading": False}]]

    cleaned = apply_cleanup_flags(pages, [])

    assert cleaned == pages


def test_apply_cleanup_flags_applies_more_than_one_flag_in_sequence():
    # The manifest supports "one or more" cleanup flags per document
    # (ADR-0016, issue #9) -- no single real document in this corpus needs
    # both flags at once, but the mechanism itself must genuinely chain
    # multiple flags, not just work for a single-flag list. Each flag's
    # effect is independently verifiable here: the Irish section (matched by
    # heading text) is gone, and so is the navigation-chrome line (matched
    # by its own, unrelated pattern) that was sitting right next to it.
    pages = [
        [
            {"text": "Réamhrá", "is_heading": True},
            {"text": "Irish duplicate content.", "is_heading": False},
        ],
        [
            {"text": "Global risk assessment", "is_heading": True},
            {"text": "Annex 1 >  | Annex 2  | Annex 3  | Annex 4", "is_heading": False},
            {"text": "Real content.", "is_heading": False},
        ],
    ]

    cleaned = apply_cleanup_flags(pages, ["bilingual_duplicate_content", "navigation_chrome"])

    assert cleaned[0] == []
    assert cleaned[1] == [
        {"text": "Global risk assessment", "is_heading": True},
        {"text": "Real content.", "is_heading": False},
    ]


def test_apply_cleanup_flags_raises_on_an_unrecognized_flag_name():
    # An unrecognized flag is almost certainly a typo in the manifest, not a
    # genuinely empty set of cleanup rules -- this should raise loudly
    # (ADR-0019's "fail loudly" reasoning, applied here the same way an
    # unrecognized chunking_strategy already raises in pipeline.py), not
    # silently do nothing.
    with pytest.raises(KeyError):
        apply_cleanup_flags([[{"text": "x", "is_heading": False}]], ["not_a_real_flag"])
