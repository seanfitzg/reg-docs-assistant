# Keyword search over the active Chunks, for hand-writing Eval Cases: find
# the passage, then copy its exact (document_id, locator) into
# eval/dataset.json rather than typing it from memory.
#
#   python -m regdocs_eval.find_locator "key information document"
#   python -m regdocs_eval.find_locator "fitness probity" --doc doc-10-cp160-fitness-and-probity-regime
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

from regdocs_eval.corpus import DEFAULT_OUTPUT_DIR, load_active_chunks

# How many characters of context to show either side of the first match.
SNIPPET_CONTEXT = 80


# Deliberately not called a "hit": in CONTEXT.md that word means a retrieved
# Chunk matching a Gold Locator under ADR-0028's rule, which a keyword result
# is not.
@dataclass(frozen=True)
class KeywordMatch:
    document_id: str
    locator: str
    snippet: str


def search(
    chunks: list[dict], terms: str, document_id: str | None = None
) -> list[KeywordMatch]:
    """Chunks containing every whitespace-separated term, case-insensitively.

    Terms are ANDed rather than matched as one phrase, because PDF
    extraction leaves line breaks and double spaces mid-sentence -- an exact
    phrase would miss "comprehensive\\nconsumer".
    """
    wanted = [t.lower() for t in terms.split()]

    # Must be rejected explicitly: all() over no terms is vacuously True, so
    # every Chunk would match and wanted[0] below would raise IndexError.
    if not wanted:
        raise ValueError("search needs at least one search term")

    matches = []
    for chunk in chunks:
        # "is not None" so the filter is skipped only when no document was
        # asked for.
        if document_id is not None and chunk["document_id"] != document_id:
            continue

        # Collapse whitespace runs (newlines, tabs, repeated spaces).
        text = re.sub(r"\s+", " ", chunk["text"])
        lowered = text.lower()

        if all(term in lowered for term in wanted):
            start = lowered.find(wanted[0])
            # max(0, ...) stops a negative start wrapping to the end of the
            # string.
            snippet = text[
                max(0, start - SNIPPET_CONTEXT) : start
                + len(wanted[0])
                + SNIPPET_CONTEXT
            ]
            matches.append(
                KeywordMatch(chunk["document_id"], chunk["locator"], snippet)
            )
    return matches


# argv is injectable so tests can call main([...]) with their own arguments.
def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Find (document_id, locator) pairs by keyword."
    )
    parser.add_argument("terms", help="words that must all appear in the Chunk text")
    parser.add_argument("--doc", help="only search this document_id")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="ingestion output to search",
    )
    args = parser.parse_args(argv)

    # Report via argparse (usage line, exit status 2) rather than letting
    # search()'s ValueError surface as a traceback.
    if not args.terms.split():
        parser.error("terms must contain at least one word")

    # On Windows, piped or redirected output defaults to the legacy cp1252
    # code page, so curly quotes and bullets from the PDFs arrive as mojibake
    # in a UTF-8 terminal -- bad when this output is where answer_quote text
    # gets copied from. Force UTF-8 regardless.
    sys.stdout.reconfigure(encoding="utf-8")

    if not (args.output_dir / "chunks").is_dir():
        print(
            f"No ingestion output at {args.output_dir} -- run the ingestion pipeline first.",
            file=sys.stderr,
        )
        return 1

    chunks = load_active_chunks(args.output_dir)

    # A mistyped --doc would otherwise print "0 match(es)", which reads like
    # "not in this Document" -- say plainly that the id doesn't exist.
    document_exists = any(c["document_id"] == args.doc for c in chunks)
    if args.doc is not None and not document_exists:
        print(
            f"No Document with id {args.doc!r} in {args.output_dir}.", file=sys.stderr
        )
        return 1

    matches = search(chunks, args.terms, args.doc)
    for match in matches:
        print(f"{match.document_id}  |  {match.locator}")
        print(f"    ...{match.snippet}...")
    print(f"{len(matches)} match(es)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
