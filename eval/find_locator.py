# Keyword search over the active Chunks, for hand-writing Eval Cases: find
# the passage, then copy its exact (document_id, locator) into
# eval/dataset.json rather than typing it from memory.
#
#   python eval/find_locator.py "key information document"
#   python eval/find_locator.py "fitness probity" --doc doc-10-cp160-fitness-and-probity-regime
#
# This is plain *lexical* search on purpose: it matches words, not meaning.
# Once the eval harness runs *embedding* search over the same Chunks,
# comparing what each finds for the same question is a direct look at the
# difference -- and at why ADR-0029 tags questions by phrasing.

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path

from corpus import DEFAULT_OUTPUT_DIR, load_active_chunks

# How many characters of context to show either side of the first match.
SNIPPET_CONTEXT = 80


# @dataclass generates __init__, __eq__ and __repr__ from the annotated
# fields below -- close to a C# record. frozen=True makes instances
# immutable (assigning a field raises), like a record with init-only props.
@dataclass(frozen=True)
class Hit:
    document_id: str
    locator: str
    snippet: str


def search(chunks: list[dict], terms: str, document_id: str | None = None) -> list[Hit]:
    """Chunks containing every whitespace-separated term, case-insensitively.

    Terms are ANDed rather than matched as one phrase, because PDF
    extraction leaves line breaks and double spaces mid-sentence -- an exact
    phrase would miss "comprehensive\\nconsumer".
    """
    # .split() with no argument splits on any run of whitespace and drops
    # empty strings; .lower() makes the comparison case-insensitive.
    wanted = [t.lower() for t in terms.split()]

    hits = []
    for chunk in chunks:
        # "is not None" rather than a truthiness check, so the filter is
        # only skipped when no document was asked for at all.
        if document_id is not None and chunk["document_id"] != document_id:
            continue

        # re.sub(r"\s+", " ", ...) collapses every run of whitespace
        # (newlines, tabs, repeated spaces) into one space. The r"..."
        # prefix is a raw string: backslashes are kept literally, so "\s"
        # reaches the regex engine intact -- like a C# @"..." verbatim string.
        text = re.sub(r"\s+", " ", chunk["text"])
        lowered = text.lower()

        # all(...) is True only if every item is truthy -- LINQ's .All().
        # The argument is a generator expression, evaluated lazily and
        # stopping at the first term that's missing.
        if all(term in lowered for term in wanted):
            start = lowered.find(wanted[0])
            # Slicing text[a:b] takes characters a up to (not including) b;
            # max(0, ...) stops a negative start wrapping round to the end,
            # since negative indices count from the end in Python.
            snippet = text[max(0, start - SNIPPET_CONTEXT) : start + len(wanted[0]) + SNIPPET_CONTEXT]
            hits.append(Hit(chunk["document_id"], chunk["locator"], snippet))
    return hits


def main(argv: list[str] | None = None) -> int:
    # argparse builds a command-line parser from declarations, and prints
    # --help and usage errors for free -- similar to System.CommandLine.
    parser = argparse.ArgumentParser(description="Find (document_id, locator) pairs by keyword.")
    parser.add_argument("terms", help="words that must all appear in the Chunk text")
    parser.add_argument("--doc", help="only search this document_id")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR, help="ingestion output to search")
    args = parser.parse_args(argv)

    # On Windows, output piped or redirected (not a live console) defaults to
    # the legacy cp1252 code page, so curly quotes and bullets from the PDFs
    # arrive as mojibake in a UTF-8 terminal -- bad when this output is where
    # answer_quote text gets copied from. Force UTF-8 regardless.
    sys.stdout.reconfigure(encoding="utf-8")

    if not (args.output_dir / "chunks").is_dir():
        print(f"No ingestion output at {args.output_dir} -- run the ingestion pipeline first.", file=sys.stderr)
        return 1

    hits = search(load_active_chunks(args.output_dir), args.terms, args.doc)
    for hit in hits:
        print(f"{hit.document_id}  |  {hit.locator}")
        print(f"    ...{hit.snippet}...")
    print(f"{len(hits)} match(es)")
    return 0


# True only when this file is run directly ("python eval/find_locator.py"),
# not when a test imports it -- the usual guard, as in store/loader.py.
if __name__ == "__main__":
    sys.exit(main())
