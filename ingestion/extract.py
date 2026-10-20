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
    document = pymupdf.open(pdf_path)
    return [page.get_text() for page in document]


# pymupdf's span "flags" is a bitfield; 1 << 4 (16) is the "bold" bit.
BOLD_FLAG = 1 << 4


def extract_pages_with_headings(pdf_path: Path) -> list[list[dict]]:
    # heading_sections documents (ADR-0014) have no numbered marker a regex
    # could find, unlike clause_numbered's "1.1" -- a heading like "Purpose"
    # is distinguished only *visually*, by being bold. get_text() throws that
    # away; get_text("dict") keeps it.
    document = pymupdf.open(pdf_path)

    pages = []
    for page in document:
        # Nested: blocks -> lines -> spans (runs of same-styled text).
        page_as_dict = page.get_text("dict")

        lines_on_this_page = []
        for block in page_as_dict["blocks"]:
            # Image blocks have no "lines" key.
            if "lines" not in block:
                continue

            for line in block["lines"]:
                spans = line["spans"]
                text = "".join(span["text"] for span in spans)
                if not text.strip():
                    continue

                # A line is a heading only if EVERY span is bold; a sentence
                # with one bold word for emphasis must not count.
                is_heading = all(span["flags"] & BOLD_FLAG for span in spans)

                lines_on_this_page.append({"text": text, "is_heading": is_heading})

        pages.append(lines_on_this_page)

    return pages
