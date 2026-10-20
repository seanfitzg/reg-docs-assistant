# Tests for the academic_sections chunking strategy (ADR-0014): splitting a
# Research Technical Paper's text at bold heading lines, with the locator
# pairing the heading text with the page it starts on (ADR-0015) -- e.g.
# "Literature Review (p. 7)". Most cases mirror test_heading_sections.py; the
# "_wraps_" and "_no_body_ever_follows_" tests cover the one real difference:
# a heading here can span more than one bold line.

from strategies.academic_sections import chunk


def test_splits_on_each_heading():
    pages = [
        [
            {"text": "Introduction", "is_heading": True},
            {"text": "The introduction is X.", "is_heading": False},
            {"text": "Literature Review", "is_heading": True},
            {"text": "The review is Y.", "is_heading": False},
        ],
    ]

    chunks = chunk(pages)

    locators = [c["locator"] for c in chunks]
    assert locators == ["Introduction (p. 1)", "Literature Review (p. 1)"]


def test_chunk_text_is_everything_up_to_the_next_heading():
    pages = [
        [
            {"text": "Introduction", "is_heading": True},
            {"text": "The introduction is X.", "is_heading": False},
            {"text": "Literature Review", "is_heading": True},
            {"text": "The review is Y.", "is_heading": False},
        ],
    ]

    chunks = chunk(pages)

    assert chunks[0]["text"] == "The introduction is X."
    assert chunks[1]["text"] == "The review is Y."


def test_locator_uses_the_page_the_heading_starts_on_not_page_one():
    pages = [
        [
            {"text": "Introduction", "is_heading": True},
            {"text": "Intro text.", "is_heading": False},
        ],
        [
            {"text": "Results", "is_heading": True},
            {"text": "Results text.", "is_heading": False},
        ],
    ]

    chunks = chunk(pages)

    assert chunks[0]["locator"] == "Introduction (p. 1)"
    assert chunks[1]["locator"] == "Results (p. 2)"


def test_a_section_can_continue_across_a_page_boundary_with_no_new_heading():
    pages = [
        [
            {"text": "Results", "is_heading": True},
            {"text": "First part.", "is_heading": False},
        ],
        [{"text": "Second part, still under Results.", "is_heading": False}],
    ]

    chunks = chunk(pages)

    assert len(chunks) == 1
    assert chunks[0]["locator"] == "Results (p. 1)"
    assert chunks[0]["text"] == "First part.\nSecond part, still under Results."


def test_text_before_the_first_heading_is_discarded():
    pages = [
        [
            {"text": "Research Technical Paper", "is_heading": False},
            {"text": "Introduction", "is_heading": True},
            {"text": "The introduction is X.", "is_heading": False},
        ],
    ]

    chunks = chunk(pages)

    assert len(chunks) == 1
    assert chunks[0]["locator"] == "Introduction (p. 1)"


def test_no_headings_produces_no_chunks():
    pages = [[{"text": "Just a paragraph, no headings anywhere.", "is_heading": False}]]

    chunks = chunk(pages)

    assert chunks == []


def test_a_heading_that_wraps_across_two_bold_lines_is_joined_into_one_locator():
    # Found on the real RTP07/19 PDF: Appendix A's heading is two consecutive
    # bold lines ("A Sources and Construction of Variables Used in Panel" /
    # "Regressions"), one heading split by layout. Unlike heading_sections
    # (written for DP8, where back-to-back bold lines are a spurious
    # cover-page/ToC entry before a real heading), this strategy joins them.
    pages = [
        [
            {
                "text": "A Sources and Construction of Variables Used in Panel",
                "is_heading": True,
            },
            {"text": "Regressions", "is_heading": True},
            {
                "text": "For the policy rates we use a 3-month rate.",
                "is_heading": False,
            },
        ],
    ]

    chunks = chunk(pages)

    assert len(chunks) == 1
    assert (
        chunks[0]["locator"]
        == "A Sources and Construction of Variables Used in Panel Regressions (p. 1)"
    )
    assert chunks[0]["text"] == "For the policy rates we use a 3-month rate."


def test_a_heading_run_does_not_continue_across_a_page_boundary():
    # A join is only allowed within a single page (module comment).
    # chunk_document() strips boilerplate before chunk() sees the pages, so a
    # footer stripped from the bottom of page 1 and a header from the top of
    # page 2 would make two *unrelated* headings across the break look like a
    # wrapped one. "Trailing Heading" stands in for a heading that had a
    # footer after it, already removed by clean.py: it never reaches a body
    # line, so (the "no empty chunk" guarantee) it's dropped rather than
    # merged into the next page's heading.
    pages = [
        [{"text": "Trailing Heading", "is_heading": True}],
        [
            {"text": "Real Heading", "is_heading": True},
            {"text": "Real body text.", "is_heading": False},
        ],
    ]

    chunks = chunk(pages)

    assert len(chunks) == 1
    assert chunks[0]["locator"] == "Real Heading (p. 2)"


def test_a_heading_with_no_body_text_ever_following_it_produces_no_chunk():
    # The last lines are all bold, so no body text completes that heading's
    # section and it never becomes a chunk: heading_sections' "no empty
    # chunk" guarantee, reached via the pending-heading-lines path.
    pages = [
        [
            {"text": "Conclusions", "is_heading": True},
            {"text": "MMFs responded to policy as expected.", "is_heading": False},
            {"text": "References", "is_heading": True},
        ],
    ]

    chunks = chunk(pages)

    assert len(chunks) == 1
    assert chunks[0]["locator"] == "Conclusions (p. 1)"
