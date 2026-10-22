# Tests for ids.py: the id-derivation functions that keep any id from being
# hand-typed (ADR-0017 for Document, extended to Generation and Chunk ids).

from regdocs_ingestion.ids import chunk_id, document_id_from_filename, generation_id


# ---- Document id ----


def test_document_id_is_derived_from_filename_stem():
    # ADR-0017's own example: "21-new-doc.pdf" -> "doc-21-new-doc".
    assert document_id_from_filename("21-new-doc.pdf") == "doc-21-new-doc"


def test_document_id_strips_the_pdf_extension_not_just_dots_in_the_name():
    # The stem avoids mangling a name that contains a dot elsewhere.
    assert (
        document_id_from_filename("03-cp47-review-of-consumer-protection-code.pdf")
        == "doc-03-cp47-review-of-consumer-protection-code"
    )


# ---- Chunking Generation id ----


def test_generation_id_is_derived_from_document_id_and_generation_number():
    assert generation_id("doc-03-cp47", 1) == "doc-03-cp47-gen-1"


def test_generation_id_differs_for_a_later_generation_of_the_same_document():
    # Re-chunking adds a generation (ADR-0003); two numbers never collide.
    first = generation_id("doc-03-cp47", 1)
    second = generation_id("doc-03-cp47", 2)

    assert first != second


# ---- Chunk id ----


def test_chunk_id_is_derived_from_generation_id_and_sequence_number():
    assert chunk_id("doc-03-cp47-gen-1", 1) == "doc-03-cp47-gen-1-chunk-001"


def test_chunk_id_zero_pads_the_sequence_number():
    # Zero-padding keeps string sort order equal to document order
    # (chunk-010 after chunk-002, not before).
    assert chunk_id("doc-03-cp47-gen-1", 10) == "doc-03-cp47-gen-1-chunk-010"
