# Tests for clean.py (ADR-0016), in two parts: the automatic cleanup (running
# headers/footers, plus bare page-number lines, which don't repeat verbatim
# but are just as mechanical to remove), and the manifest-flagged cleanup
# (issue #9, generalised in #13), which runs only when a manifest entry names
# it.

import pytest

from regdocs_ingestion.clean import (
    apply_cleanup_flags,
    strip_headers_footers_and_page_numbers,
    strip_headers_footers_and_page_numbers_from_layout,
    strip_lines_with_repeated_pattern,
    strip_section_between_headings,
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
    # A header style can be confined to one section: the real CP54 PDF's
    # running header prints on only 15 of 96 pages (the rest is the appended
    # draft Code under a different header), so neither "every page" nor "a
    # majority" would fire. What this synthetic case shares with it is a line
    # repeating far more often than real prose would: 5 of 20 pages.
    pages = [
        ("Running Header\nReal page content." if i < 5 else f"Page {i} unique content.")
        for i in range(20)
    ]

    cleaned = strip_headers_footers_and_page_numbers(pages)

    for page_text in cleaned[:5]:
        assert "Running Header" not in page_text


def test_line_only_on_one_page_is_not_treated_as_a_header():
    # ADR-0016 chose a mechanical repetition rule because it has no real
    # false-positive risk; a line that shows up once must never be touched.
    pages = [
        "1.1\nPurpose",
        "1.2\nScope",
    ]

    cleaned = strip_headers_footers_and_page_numbers(pages)

    assert "Purpose" in cleaned[0]
    assert "Scope" in cleaned[1]


def test_bare_page_number_lines_are_stripped():
    # Page numbers never repeat verbatim, so they need their own rule: a line
    # of *only* digits is a page number on essentially any document.
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
    # DP8's real footer is "Page 5", "Page 6", ...: neither a verbatim repeat
    # nor caught by the bare-digit rule. No real sentence is just "Page"
    # followed by a number, so it's equally safe to strip.
    pages = ["Page 5\nReal text on page five.", "Page 6\nReal text on page six."]

    cleaned = strip_headers_footers_and_page_numbers(pages)

    assert "Page 5" not in cleaned[0].splitlines()
    assert "Page 6" not in cleaned[1].splitlines()
    assert "Real text on page five." in cleaned[0]


def test_a_number_that_is_part_of_real_text_is_kept():
    # A clause locator like "1.1" or a sentence containing a number must
    # survive.
    pages = ["1.1\nThe fee is 30 days.", "1.2\nMore text."]

    cleaned = strip_headers_footers_and_page_numbers(pages)

    assert "1.1" in cleaned[0]
    assert "The fee is 30 days." in cleaned[0]


# ---- Layout-aware variant, for heading_sections documents ----
#
# heading_sections needs to know *which* surviving lines are headings
# ("is_heading"), so this variant works on the list[list[dict]] shape but
# applies the same boilerplate rules.


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
    # Distinct content per page: identical content would itself trigger the
    # header/footer rule.
    pages = [
        [
            {"text": "Page 5", "is_heading": False},
            {"text": "Content on five.", "is_heading": False},
        ],
        [
            {"text": "Page 6", "is_heading": False},
            {"text": "Content on six.", "is_heading": False},
        ],
    ]

    cleaned = strip_headers_footers_and_page_numbers_from_layout(pages)

    assert cleaned[0] == [{"text": "Content on five.", "is_heading": False}]


# ---- Manifest-flagged cleanup (ADR-0016) ----
#
# These run only when a manifest entry names them (issue #9), so every test
# builds its own small fixture. Both functions are parameterised (issue #13):
# FSR's and DP7's real quirks appear only in comments as motivating examples,
# and most fixtures use invented headings/patterns to prove the functions
# aren't still tied to one real document.


def test_strip_section_between_headings_removes_the_span_between_markers():
    pages = [
        [
            {"text": "Preface", "is_heading": True},
            {"text": "English preface content.", "is_heading": False},
        ],
        [
            {"text": "Withdrawn Notice", "is_heading": True},
            {"text": "Superseded content.", "is_heading": False},
        ],
        [
            {"text": "Real Section", "is_heading": True},
            {"text": "Real content resumes here.", "is_heading": False},
        ],
    ]

    cleaned = strip_section_between_headings(
        pages, start_heading="Withdrawn Notice", end_heading="Real Section"
    )

    assert cleaned[0] == [
        {"text": "Preface", "is_heading": True},
        {"text": "English preface content.", "is_heading": False},
    ]
    assert cleaned[1] == []
    assert cleaned[2] == [
        {"text": "Real Section", "is_heading": True},
        {"text": "Real content resumes here.", "is_heading": False},
    ]


def test_strip_section_between_headings_spanning_multiple_pages_is_removed():
    # Mirrors FSR's shape (Réamhrá -> Forbhreathnú -> a page with no heading
    # -> Global risk assessment): the removal must survive page boundaries.
    pages = [
        [
            {"text": "Start", "is_heading": True},
            {"text": "Page one.", "is_heading": False},
        ],
        [
            {"text": "Middle Heading", "is_heading": True},
            {"text": "Page two.", "is_heading": False},
        ],
        [{"text": "Page three, no heading here.", "is_heading": False}],
        [
            {"text": "End", "is_heading": True},
            {"text": "Real content.", "is_heading": False},
        ],
    ]

    cleaned = strip_section_between_headings(
        pages, start_heading="Start", end_heading="End"
    )

    assert cleaned[0] == []
    assert cleaned[1] == []
    assert cleaned[2] == []
    assert cleaned[3] == [
        {"text": "End", "is_heading": True},
        {"text": "Real content.", "is_heading": False},
    ]


def test_strip_section_between_headings_ignores_other_bold_lines_inside_the_span():
    # FSR's Réamhrá/Forbhreathnú sections come out of extraction with their
    # *entire* body marked is_heading=True (it's bold, and a bold paragraph
    # can't be told from a heading). A naive "any heading exits the zone" rule
    # would stop removing right after the start marker. This bold line isn't
    # the configured end marker, so it must not end the removal.
    pages = [
        [
            {"text": "Start", "is_heading": True},
            {
                "text": "This whole line is bold too, but isn't the end marker.",
                "is_heading": True,
            },
            {"text": "End", "is_heading": True},
            {"text": "Real content.", "is_heading": False},
        ],
    ]

    cleaned = strip_section_between_headings(
        pages, start_heading="Start", end_heading="End"
    )

    assert cleaned[0] == [
        {"text": "End", "is_heading": True},
        {"text": "Real content.", "is_heading": False},
    ]


def test_strip_section_between_headings_with_no_matching_markers_is_unaffected():
    pages = [
        [
            {"text": "Purpose", "is_heading": True},
            {"text": "Ordinary content.", "is_heading": False},
        ],
    ]

    cleaned = strip_section_between_headings(
        pages, start_heading="Start", end_heading="End"
    )

    assert cleaned == pages


def test_strip_lines_with_repeated_pattern_removes_a_line_meeting_the_threshold():
    # Modelled on DP7's Annex nav-breadcrumb footer ("Annex 1 page 1 of 3 >  |
    # Annex 2  | Annex 3  | Annex 4"), whose "page X of Y" part changes each
    # time, so it never repeats verbatim (ADR-0016). An invented "Widget"
    # pattern proves the function carries no real document's wording.
    pages = [
        [
            {
                "text": "Widget 1 >  | Widget 2  | Widget 3  | Widget 4",
                "is_heading": True,
            },
            {"text": "Real content.", "is_heading": False},
        ],
    ]

    cleaned = strip_lines_with_repeated_pattern(
        pages, pattern=r"Widget \d", minimum_matches=4
    )

    assert cleaned[0] == [{"text": "Real content.", "is_heading": False}]


def test_strip_lines_with_repeated_pattern_keeps_a_line_below_the_threshold():
    # DP7's Table of Contents lists "Annex 1".."Annex 4" as four *separate*
    # lines: real content that must survive, as must a sentence mentioning the
    # pattern once.
    pages = [
        [
            {"text": "Widget 1", "is_heading": False},
            {"text": "Widget 2", "is_heading": False},
            {"text": "See the detail in Widget 2.", "is_heading": False},
        ],
    ]

    cleaned = strip_lines_with_repeated_pattern(
        pages, pattern=r"Widget \d", minimum_matches=4
    )

    assert cleaned == pages


def test_strip_lines_with_repeated_pattern_is_case_insensitive():
    pages = [[{"text": "widget 1  widget 2  WIDGET 3  Widget 4", "is_heading": False}]]

    cleaned = strip_lines_with_repeated_pattern(
        pages, pattern=r"widget \d", minimum_matches=4
    )

    assert cleaned[0] == []


def test_apply_cleanup_flags_runs_the_named_flag_type_with_its_parameters():
    pages = [
        [
            {
                "text": "Widget 1 >  | Widget 2  | Widget 3  | Widget 4",
                "is_heading": False,
            }
        ],
    ]

    cleaned = apply_cleanup_flags(
        pages,
        [{"type": "navigation_chrome", "pattern": r"Widget \d", "minimum_matches": 4}],
    )

    assert cleaned[0] == []


def test_apply_cleanup_flags_with_no_flags_is_a_no_op():
    pages = [[{"text": "Untouched.", "is_heading": False}]]

    cleaned = apply_cleanup_flags(pages, [])

    assert cleaned == pages


def test_apply_cleanup_flags_applies_more_than_one_flag_in_sequence():
    # The manifest allows several flags per document (ADR-0016, issue #9).
    # No real document needs two, but the mechanism must chain them: both the
    # removed section and the unrelated navigation-chrome line next to it
    # are gone.
    pages = [
        [
            {"text": "Start", "is_heading": True},
            {"text": "Removed content.", "is_heading": False},
        ],
        [
            {"text": "End", "is_heading": True},
            {
                "text": "Widget 1 >  | Widget 2  | Widget 3  | Widget 4",
                "is_heading": False,
            },
            {"text": "Real content.", "is_heading": False},
        ],
    ]

    cleaned = apply_cleanup_flags(
        pages,
        [
            {
                "type": "duplicate_section_removal",
                "start_heading": "Start",
                "end_heading": "End",
            },
            {
                "type": "navigation_chrome",
                "pattern": r"Widget \d",
                "minimum_matches": 4,
            },
        ],
    )

    assert cleaned[0] == []
    assert cleaned[1] == [
        {"text": "End", "is_heading": True},
        {"text": "Real content.", "is_heading": False},
    ]


def test_apply_cleanup_flags_raises_on_an_unrecognized_flag_type():
    # Almost certainly a manifest typo, so it must raise, as an unrecognized
    # chunking_strategy does in pipeline.py (ADR-0019), not silently do
    # nothing.
    with pytest.raises(KeyError):
        apply_cleanup_flags(
            [[{"text": "x", "is_heading": False}]], [{"type": "not_a_real_flag_type"}]
        )


def test_apply_cleanup_flags_raises_on_a_flag_with_a_mismatched_parameter_name():
    # Flag parameters pass straight through as kwargs, so a manifest typo like
    # "min_matches" must fail loudly, not apply some unintended default.
    with pytest.raises(TypeError):
        apply_cleanup_flags(
            [[{"text": "x", "is_heading": False}]],
            [{"type": "navigation_chrome", "pattern": r"Widget \d", "min_matches": 4}],
        )
