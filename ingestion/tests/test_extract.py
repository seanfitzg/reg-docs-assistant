# Tests for extract.py, the thin pymupdf wrapper that turns a PDF into one
# text string per page. A unit test shouldn't need the corpus (not in git, see
# corpus/SOURCES.md), so each builds a tiny throwaway PDF with pymupdf and
# checks extraction round-trips its text. Real PDFs are covered end to end in
# test_pipeline.py.

import pymupdf

from regdocs_ingestion.extract import extract_pages, extract_pages_with_headings


def test_extract_pages_returns_one_string_per_page(tmp_path):
    document = pymupdf.open()
    page_one = document.new_page()
    page_one.insert_text((72, 72), "Page one text.")
    page_two = document.new_page()
    page_two.insert_text((72, 72), "Page two text.")

    pdf_path = tmp_path / "scratch.pdf"
    document.save(pdf_path)

    pages = extract_pages(pdf_path)

    assert len(pages) == 2
    assert "Page one text." in pages[0]
    assert "Page two text." in pages[1]


def test_extract_pages_with_headings_flags_bold_lines_as_headings(tmp_path):
    # "hebo"/"helv" are built-in Helvetica-Bold and Helvetica. Real headings
    # are detected the same way: every character in a bold-flagged font.
    document = pymupdf.open()
    page = document.new_page()
    page.insert_text((72, 72), "A Heading", fontname="hebo", fontsize=14)
    page.insert_text((72, 100), "Regular body text.", fontname="helv", fontsize=10)

    pdf_path = tmp_path / "scratch.pdf"
    document.save(pdf_path)

    pages = extract_pages_with_headings(pdf_path)

    assert len(pages) == 1
    lines = pages[0]
    heading_line = next(line for line in lines if line["text"] == "A Heading")
    body_line = next(line for line in lines if line["text"] == "Regular body text.")
    assert heading_line["is_heading"] is True
    assert body_line["is_heading"] is False
