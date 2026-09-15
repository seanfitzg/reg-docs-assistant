# Id derivation for Document, Chunking Generation, and Chunk records.
#
# Every id here is *computed*, never invented by hand — for Document
# specifically this is ADR-0017's decision (a filename-derived id removes a
# whole class of typo/duplicate/drift mistakes); Chunking Generation and
# Chunk ids extend the same reasoning, since nothing in the system needs
# these to be independently chosen, only stable and unique.

from pathlib import Path


def document_id_from_filename(filename: str) -> str:
    # Path(...).stem is the filename with its final extension removed —
    # "03-cp47-review-of-consumer-protection-code.pdf" -> "03-cp47-review-
    # of-consumer-protection-code". This is safer than a plain string
    # ".replace('.pdf', '')", which would also mangle a ".pdf" appearing
    # anywhere else in the name, not just at the end.
    stem = Path(filename).stem
    return f"doc-{stem}"


def generation_id(document_id: str, generation_number: int) -> str:
    # An f-string ("formatted string literal") — the f prefix lets {...}
    # placeholders inside the string be evaluated as Python expressions and
    # substituted in, the same idea as C#'s $"...{expr}..." interpolation.
    return f"{document_id}-gen-{generation_number}"


def chunk_id(chunking_generation_id: str, sequence_number: int) -> str:
    # ":03d" is a format spec: format this value as a decimal integer ("d"),
    # zero-padded to at least 3 digits ("03") -- e.g. 1 -> "001", 10 ->
    # "010". Directly comparable to C#'s "{0:D3}" / sequence.ToString("D3").
    return f"{chunking_generation_id}-chunk-{sequence_number:03d}"
