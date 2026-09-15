# Test for extract.py, the thin pymupdf wrapper that turns a PDF into one
# text string per page. Rather than depending on a real corpus PDF here (the
# corpus isn't committed to git -- see corpus/SOURCES.md -- and a unit test
# shouldn't need gigabytes of regulatory PDFs to run), this builds a tiny
# throwaway PDF from scratch with pymupdf itself and checks extraction
# round-trips its known text. The real corpus PDF is exercised separately,
# by the end-to-end pipeline test in test_pipeline.py.

import pymupdf

from extract import extract_pages


def test_extract_pages_returns_one_string_per_page(tmp_path):
    # tmp_path is a built-in pytest fixture: a Path to a fresh temporary
    # directory, unique to this test, cleaned up automatically afterwards --
    # pytest supplies it automatically because it's named as a parameter
    # here, no manual setup/teardown required (similar in spirit to how a
    # test base class might hand you a scratch directory in other
    # frameworks, but wired up per-parameter instead of via inheritance).
    document = pymupdf.open()  # open() with no path creates a new, empty PDF
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
