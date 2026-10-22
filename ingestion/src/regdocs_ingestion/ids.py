# Id derivation for Document, Chunking Generation, and Chunk records.
#
# Every id here is *computed*, never invented by hand -- for Document this is
# ADR-0017's decision (a filename-derived id removes a class of
# typo/duplicate/drift mistakes); Chunking Generation and Chunk ids extend the
# same reasoning, since they only need to be stable and unique.

from pathlib import Path


def document_id_from_filename(filename: str) -> str:
    # Path.stem drops only the final extension, unlike .replace('.pdf', '')
    # which would also mangle a ".pdf" elsewhere in the name.
    stem = Path(filename).stem
    return f"doc-{stem}"


def generation_id(document_id: str, generation_number: int) -> str:
    return f"{document_id}-gen-{generation_number}"


def chunk_id(chunking_generation_id: str, sequence_number: int) -> str:
    # Zero-padded to 3 digits: 1 -> "001".
    return f"{chunking_generation_id}-chunk-{sequence_number:03d}"
