# Tests for ids.py: the three id-derivation functions the pipeline uses so
# that no id is ever hand-typed (ADR-0017 for Document; the same reasoning
# is extended here to Chunking Generation and Chunk ids, for the same
# reason — determinism over invention).

from ids import chunk_id, document_id_from_filename, generation_id


# ---- Document id ----

def test_document_id_is_derived_from_filename_stem():
    # ADR-0017's own example: "21-new-doc.pdf" -> "doc-21-new-doc".
    assert document_id_from_filename("21-new-doc.pdf") == "doc-21-new-doc"


def test_document_id_strips_the_pdf_extension_not_just_dots_in_the_name():
    # A naive "replace .pdf" could mangle a filename that happens to contain
    # a dot elsewhere; using the filename's *stem* (everything before the
    # final extension) avoids that regardless of what's earlier in the name.
    assert document_id_from_filename("03-cp47-review-of-consumer-protection-code.pdf") \
        == "doc-03-cp47-review-of-consumer-protection-code"


# ---- Chunking Generation id ----

def test_generation_id_is_derived_from_document_id_and_generation_number():
    assert generation_id("doc-03-cp47", 1) == "doc-03-cp47-gen-1"


def test_generation_id_differs_for_a_later_generation_of_the_same_document():
    # Re-chunking a Document produces a fresh, additional generation
    # (ADR-0003) -- proving two generation numbers for the same document
    # never collide.
    first = generation_id("doc-03-cp47", 1)
    second = generation_id("doc-03-cp47", 2)

    assert first != second


# ---- Chunk id ----

def test_chunk_id_is_derived_from_generation_id_and_sequence_number():
    assert chunk_id("doc-03-cp47-gen-1", 1) == "doc-03-cp47-gen-1-chunk-001"


def test_chunk_id_zero_pads_the_sequence_number():
    # Zero-padding keeps ids sorting in document order as plain strings
    # (chunk-001, chunk-002, ..., chunk-010) rather than lexicographically
    # misordering ("chunk-1", "chunk-10", "chunk-2", ...).
    assert chunk_id("doc-03-cp47-gen-1", 10) == "doc-03-cp47-gen-1-chunk-010"
