# Text extraction: turns a PDF file into one raw text string per page.
#
# pymupdf was chosen over pypdf after a real comparison against this
# corpus: pypdf produced corrupted, unusable text on the Research Technical
# Papers (garbled glyphs/ligatures), while pymupdf extracted them cleanly
# with no regression on documents pypdf already handled fine, and ran
# roughly 7x faster than the other clean option (pdfplumber).

from pathlib import Path

import pymupdf


def extract_pages(pdf_path: Path) -> list[str]:
    # "-> list[str]" is a return-type hint: this function returns a list of
    # strings -- Python's built-in spelling of C#'s List<string>. Like all
    # type hints in this project, it's documentation only, not enforced at
    # runtime.

    # pymupdf.open(path) loads the PDF; the resulting Document object
    # supports iteration, yielding one Page object per page in order --
    # comparable to iterating a collection with foreach in C#.
    document = pymupdf.open(pdf_path)

    # page.get_text() returns the page's text as a single string, with "\n"
    # separating lines. This list comprehension builds one such string per
    # page, in page order.
    return [page.get_text() for page in document]


# pymupdf represents each span of text (a run of characters sharing one
# font/size/style) with a "flags" integer -- a bitfield where each bit
# means something different (bold, italic, etc.), the same idea as C#'s
# [Flags] enum where you combine values with |. 1 << 4 is "the number 1,
# shifted left 4 bits" = 16 = the bit that means "this span is bold".
# Checking a bit is set is span["flags"] & BOLD_FLAG -- bitwise AND, the
# same operator C# uses for the same purpose.
BOLD_FLAG = 1 << 4


def extract_pages_with_headings(pdf_path: Path) -> list[list[dict]]:
    # This function exists because heading_sections documents (ADR-0014)
    # have no numbered marker a plain-text regex could find, unlike
    # clause_numbered's "1.1" -- the only signal distinguishing a heading
    # like "Purpose" from an ordinary sentence is *visual*: it's bold, the
    # surrounding body text isn't. get_text() (used by extract_pages above)
    # throws that formatting away entirely; get_text("dict") keeps it, at
    # the cost of a far more nested structure to walk.
    document = pymupdf.open(pdf_path)

    pages = []
    for page in document:
        # get_text("dict") returns a nested structure: the page is a list
        # of "blocks" (roughly, paragraphs/regions), each block a list of
        # "lines", each line a list of "spans" (runs of same-styled text).
        page_as_dict = page.get_text("dict")

        lines_on_this_page = []
        for block in page_as_dict["blocks"]:
            # Image blocks have no "lines" key at all -- "lines" not in
            # block is Python's membership test for "this key is missing",
            # the same check dict.ContainsKey(...) would do in C#, just
            # spelled as an operator instead of a method call.
            if "lines" not in block:
                continue

            for line in block["lines"]:
                spans = line["spans"]
                # "".join(...) concatenates every span's text into one
                # string for the line -- equivalent to string.Concat(...)
                # or string.Join("", ...) in C#.
                text = "".join(span["text"] for span in spans)
                if not text.strip():
                    continue

                # all(...) is true only if every element satisfies the
                # condition -- Python's built-in for what LINQ's
                # spans.All(s => ...) does in C#. A line only counts as a
                # heading if EVERY span on it is bold; a sentence with just
                # one bold word in the middle (used for emphasis, not as a
                # section title) must not be mistaken for one.
                is_heading = all(span["flags"] & BOLD_FLAG for span in spans)

                lines_on_this_page.append({"text": text, "is_heading": is_heading})

        pages.append(lines_on_this_page)

    return pages
