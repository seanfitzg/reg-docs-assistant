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
    # pymupdf.open(path) loads the PDF; the resulting Document object
    # supports iteration, yielding one Page object per page in order --
    # comparable to iterating a collection with foreach in C#.
    document = pymupdf.open(pdf_path)

    # page.get_text() returns the page's text as a single string, with "\n"
    # separating lines. This list comprehension builds one such string per
    # page, in page order.
    return [page.get_text() for page in document]
