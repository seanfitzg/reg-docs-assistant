# Tests for the academic_sections chunking strategy (ADR-0014): splitting a
# Research Technical Paper's text at bold heading lines, with the locator
# pairing the heading text with the page it starts on (ADR-0015) -- e.g.
# "Literature Review (p. 7)". Same input/output shape as
# test_heading_sections.py (chunk() takes the list[list[dict]] shape
# extract_pages_with_headings() produces), so most of these mirror that
# file's cases directly. The cases new to this file (the "_wraps_" and
# "_no_body_ever_follows_" tests below) cover the one real behavioural
# difference: a heading here can span more than one bold line, which
# heading_sections never had to handle for DP8.

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

    assert [c["locator"] for c in chunks] == ["Introduction (p. 1)", "Literature Review (p. 1)"]


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
        [{"text": "Introduction", "is_heading": True}, {"text": "Intro text.", "is_heading": False}],
        [{"text": "Results", "is_heading": True}, {"text": "Results text.", "is_heading": False}],
    ]

    chunks = chunk(pages)

    assert chunks[0]["locator"] == "Introduction (p. 1)"
    assert chunks[1]["locator"] == "Results (p. 2)"


def test_a_section_can_continue_across_a_page_boundary_with_no_new_heading():
    pages = [
        [{"text": "Results", "is_heading": True}, {"text": "First part.", "is_heading": False}],
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
    # Found on the real RTP07/19 PDF: its Appendix A heading is two
    # consecutive bold lines ("A Sources and Construction of Variables Used
    # in Panel" / "Regressions") with nothing else between them -- one
    # heading split across a line break by the PDF's layout, not two
    # separate sections. Unlike heading_sections (written for DP8, where
    # back-to-back bold lines are a spurious cover-page/ToC entry directly
    # followed by a real heading), this strategy joins them.
    pages = [
        [
            {"text": "A Sources and Construction of Variables Used in Panel", "is_heading": True},
            {"text": "Regressions", "is_heading": True},
            {"text": "For the policy rates we use a 3-month rate.", "is_heading": False},
        ],
    ]

    chunks = chunk(pages)

    assert len(chunks) == 1
    assert chunks[0]["locator"] == "A Sources and Construction of Variables Used in Panel Regressions (p. 1)"
    assert chunks[0]["text"] == "For the policy rates we use a 3-month rate."


def test_a_heading_run_does_not_continue_across_a_page_boundary():
    # A join is only allowed within a single page (module docstring):
    # chunk_document() strips boilerplate -- running headers/footers, bare
    # page numbers -- before chunk() ever sees the pages, so a footer
    # stripped off the bottom of page 1 and a header stripped off the top
    # of page 2 would otherwise make two *unrelated* headings either side
    # of that page break look exactly like one back-to-back run, the same
    # shape a real same-page wrap has. "Trailing Heading" here stands in
    # for a heading that, in the real PDF, would have had a footer after it
    # that clean.py already removed by the time chunk() runs -- it never
    # reaches a body line of its own, so (same "no empty chunk" guarantee
    # as elsewhere) it's silently dropped rather than merged into the next
    # page's real heading.
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
    # The very last lines in the document are all bold -- there's no body
    # text left to complete that heading's section, so it never becomes a
    # citable chunk. Same "no empty chunk" guarantee heading_sections gives,
    # reached here via the pending-heading-lines path instead.
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
