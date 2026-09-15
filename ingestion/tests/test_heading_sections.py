# Tests for the heading_sections chunking strategy (ADR-0014): splitting a
# narrative document's text at bold heading lines, with the locator pairing
# the heading text with the page it starts on (ADR-0015) -- e.g.
# "Purpose (p. 5)", not just "Purpose" (which isn't unique or locatable on
# its own in a long document) or a bare page number (which would throw
# away the heading, defeating the point of a *heading*-based strategy).
#
# Unlike clause_numbered.chunk(), which works over a single joined string,
# this works over the list[list[dict]] shape extract_pages_with_headings()
# (via clean.py's layout-aware variant) produces -- each page's list of
# {"text", "is_heading"} lines -- because it needs to know both which lines
# are headings and which page each one is on.

from strategies.heading_sections import chunk


def test_splits_on_each_heading():
    pages = [
        [
            {"text": "Purpose", "is_heading": True},
            {"text": "The purpose is X.", "is_heading": False},
            {"text": "Background", "is_heading": True},
            {"text": "The background is Y.", "is_heading": False},
        ],
    ]

    chunks = chunk(pages)

    assert [c["locator"] for c in chunks] == ["Purpose (p. 1)", "Background (p. 1)"]


def test_chunk_text_is_everything_up_to_the_next_heading():
    pages = [
        [
            {"text": "Purpose", "is_heading": True},
            {"text": "The purpose is X.", "is_heading": False},
            {"text": "Background", "is_heading": True},
            {"text": "The background is Y.", "is_heading": False},
        ],
    ]

    chunks = chunk(pages)

    assert chunks[0]["text"] == "The purpose is X."
    assert chunks[1]["text"] == "The background is Y."


def test_locator_uses_the_page_the_heading_starts_on_not_page_one():
    pages = [
        [{"text": "Introduction", "is_heading": True}, {"text": "Intro text.", "is_heading": False}],
        [{"text": "Findings", "is_heading": True}, {"text": "Findings text.", "is_heading": False}],
    ]

    chunks = chunk(pages)

    assert chunks[0]["locator"] == "Introduction (p. 1)"
    assert chunks[1]["locator"] == "Findings (p. 2)"


def test_a_section_can_continue_across_a_page_boundary_with_no_new_heading():
    # A heading on page 1 whose body text runs onto page 2 (no heading
    # there) must still produce one chunk, locator anchored at page 1 --
    # not silently truncated at the page break, and not treated as a
    # second, headingless chunk.
    pages = [
        [{"text": "Overview", "is_heading": True}, {"text": "First part.", "is_heading": False}],
        [{"text": "Second part, still under Overview.", "is_heading": False}],
    ]

    chunks = chunk(pages)

    assert len(chunks) == 1
    assert chunks[0]["locator"] == "Overview (p. 1)"
    assert chunks[0]["text"] == "First part.\nSecond part, still under Overview."


def test_text_before_the_first_heading_is_discarded():
    pages = [
        [
            {"text": "Some cover-page blurb.", "is_heading": False},
            {"text": "Purpose", "is_heading": True},
            {"text": "The purpose is X.", "is_heading": False},
        ],
    ]

    chunks = chunk(pages)

    assert len(chunks) == 1
    assert chunks[0]["locator"] == "Purpose (p. 1)"


def test_a_heading_immediately_followed_by_another_heading_produces_no_empty_chunk():
    pages = [
        [
            {"text": "Empty Section", "is_heading": True},
            {"text": "Real Section", "is_heading": True},
            {"text": "Real text.", "is_heading": False},
        ],
    ]

    chunks = chunk(pages)

    assert len(chunks) == 1
    assert chunks[0]["locator"] == "Real Section (p. 1)"


def test_no_headings_produces_no_chunks():
    pages = [[{"text": "Just a paragraph, no headings anywhere.", "is_heading": False}]]

    chunks = chunk(pages)

    assert chunks == []
