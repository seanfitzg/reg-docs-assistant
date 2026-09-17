# Tests for per-document failure isolation (ADR-0019, issue #8): a document
# that can't be extracted, or whose declared chunking_strategy matches
# nothing in its text, is skipped with a surfaced error -- the rest of the
# batch still ingests, and the failing document is never persisted as a
# Document with zero Chunks.
#
# Every fixture PDF here is built from scratch with pymupdf (the same
# approach test_extract.py uses), or is deliberately not a real PDF at all
# -- these tests run unconditionally, without needing the real (not
# committed to git) corpus, because failure isolation is exactly the kind
# of behaviour that must be provable without waiting on a real document to
# happen to be broken.

import json
import logging
from pathlib import Path

import pymupdf
import pytest

from pipeline import run_pipeline

MANIFEST_ENTRY_DEFAULTS = {
    "title": "Test Document",
    "publisher": "Test Publisher",
    "published_date": "2024-01-01",
    "source_url": "https://example.test/doc.pdf",
    "supersedes": None,
}


def _write_clause_numbered_pdf(path, *, with_clauses: bool):
    # A minimal PDF built purely in-memory, saved straight to `path` --
    # mirrors test_extract.py's pattern for a throwaway fixture PDF, so no
    # real corpus file is needed to exercise either the "extracted fine,
    # strategy just found nothing" path or the "extracted fine, strategy
    # found real clauses" path.
    #
    # Three pages, each with its own distinct text, not one page repeated
    # -- clean.py's boilerplate rule (ADR-0016) treats a line as a running
    # header/footer once it repeats on min(3, page_count) pages; for a
    # single-page document that threshold is 1, so *every* line on it would
    # count as "repeated" and get stripped, silently wiping real content
    # before chunk() ever saw it. Three pages of genuinely different text
    # keeps every line's repeat count at 1, below the 3-page threshold, so
    # nothing here gets mistaken for boilerplate.
    document = pymupdf.open()
    if with_clauses:
        page_texts = [
            "1.1\nPurpose\nThe purpose is X.",
            "1.2\nScope\nThe scope is Y.",
            "1.3\nDefinitions\nThe definitions are Z.",
        ]
    else:
        page_texts = [
            "This document has no clauses at all.",
            "Still no clause numbers on this page either.",
            "Nor on this final page.",
        ]
    for page_text in page_texts:
        page = document.new_page()
        page.insert_text((72, 72), page_text)
    document.save(path)


def _write_manifest(manifest_path, entries):
    manifest_path.write_text(json.dumps(entries))


def _entry(filename, chunking_strategy):
    return {"filename": filename, "chunking_strategy": chunking_strategy, **MANIFEST_ENTRY_DEFAULTS}


def test_a_document_whose_strategy_finds_nothing_is_skipped_but_the_batch_continues(tmp_path, caplog):
    corpus_dir = tmp_path / "corpus"
    corpus_dir.mkdir()
    _write_clause_numbered_pdf(corpus_dir / "good.pdf", with_clauses=True)
    _write_clause_numbered_pdf(corpus_dir / "empty.pdf", with_clauses=False)

    manifest_path = tmp_path / "manifest.json"
    _write_manifest(manifest_path, [
        _entry("empty.pdf", "clause_numbered"),
        _entry("good.pdf", "clause_numbered"),
    ])

    # caplog is a built-in pytest fixture that captures everything logged
    # through Python's standard `logging` module during the test -- the
    # equivalent of asserting against a captured ILogger in .NET tests,
    # without needing to inject a fake logger by hand.
    with caplog.at_level(logging.ERROR):
        results = run_pipeline(manifest_path, corpus_dir, tmp_path / "output")

    # Only the good document made it into the results -- the empty one was
    # skipped, not persisted as a zero-Chunk Document.
    assert len(results) == 1
    document, chunks = results[0]
    assert document["id"] == "doc-good"
    assert len(chunks) > 0

    assert not (tmp_path / "output" / "documents" / "doc-empty.json").exists()
    assert not (tmp_path / "output" / "chunks" / "doc-empty.json").exists()
    assert (tmp_path / "output" / "documents" / "doc-good.json").exists()

    # The surfaced error names both the document and the reason.
    assert "empty.pdf" in caplog.text
    assert "clause_numbered" in caplog.text


def test_a_document_that_fails_extraction_is_skipped_but_the_batch_continues(tmp_path, caplog):
    corpus_dir = tmp_path / "corpus"
    corpus_dir.mkdir()
    _write_clause_numbered_pdf(corpus_dir / "good.pdf", with_clauses=True)
    # Not a real PDF at all -- pymupdf raises FileDataError trying to open
    # it, the same failure a genuinely corrupt downloaded file would cause.
    (corpus_dir / "corrupt.pdf").write_bytes(b"not a real pdf file, just garbage bytes")

    manifest_path = tmp_path / "manifest.json"
    _write_manifest(manifest_path, [
        _entry("corrupt.pdf", "clause_numbered"),
        _entry("good.pdf", "clause_numbered"),
    ])

    with caplog.at_level(logging.ERROR):
        results = run_pipeline(manifest_path, corpus_dir, tmp_path / "output")

    assert len(results) == 1
    document, chunks = results[0]
    assert document["id"] == "doc-good"

    assert not (tmp_path / "output" / "documents" / "doc-corrupt.json").exists()
    assert (tmp_path / "output" / "documents" / "doc-good.json").exists()

    assert "corrupt.pdf" in caplog.text


def test_a_failed_second_write_does_not_leave_an_orphaned_document_file(tmp_path, monkeypatch, caplog):
    # /code-review (issue #8) caught this: the document JSON and chunks
    # JSON are two separate write_text() calls, not one atomic operation.
    # If the second one fails after the first succeeded (a locked file, a
    # full disk -- realistic on Windows, where an antivirus can briefly
    # lock a just-created file), the old code would still log a clean
    # "skip" while leaving a Document file on disk with no matching Chunks
    # file -- exactly the "silently persisted" outcome ADR-0019 forbids,
    # just as an orphaned file instead of a zero-Chunk Document.
    corpus_dir = tmp_path / "corpus"
    corpus_dir.mkdir()
    _write_clause_numbered_pdf(corpus_dir / "good.pdf", with_clauses=True)

    manifest_path = tmp_path / "manifest.json"
    _write_manifest(manifest_path, [_entry("good.pdf", "clause_numbered")])

    # monkeypatch is a built-in pytest fixture: it replaces an attribute
    # for the duration of this test only, restoring the original
    # automatically afterwards -- pytest's version of temporarily swapping
    # in a test double, without needing a mocking library or a manual
    # try/finally to undo the swap.
    #
    # Path.write_text is an *unbound* method here (accessed on the class,
    # not an instance), so calling it takes the Path instance as its first
    # argument explicitly ("self") -- the same shape any instance method
    # has in Python once you go through the class rather than an object.
    original_write_text = Path.write_text

    def flaky_write_text(self, *args, **kwargs):
        if self.parent.name == "chunks":
            raise OSError("simulated failure writing the chunks file")
        return original_write_text(self, *args, **kwargs)

    monkeypatch.setattr(Path, "write_text", flaky_write_text)

    with caplog.at_level(logging.ERROR):
        results = run_pipeline(manifest_path, corpus_dir, tmp_path / "output")

    assert results == []
    assert not (tmp_path / "output" / "documents" / "doc-good.json").exists()
    assert "good.pdf" in caplog.text


def test_all_documents_in_a_batch_failing_produces_no_results_and_no_output_files(tmp_path, caplog):
    corpus_dir = tmp_path / "corpus"
    corpus_dir.mkdir()
    _write_clause_numbered_pdf(corpus_dir / "empty.pdf", with_clauses=False)

    manifest_path = tmp_path / "manifest.json"
    _write_manifest(manifest_path, [_entry("empty.pdf", "clause_numbered")])

    with caplog.at_level(logging.ERROR):
        results = run_pipeline(manifest_path, corpus_dir, tmp_path / "output")

    assert results == []
    assert not any((tmp_path / "output" / "documents").iterdir())
