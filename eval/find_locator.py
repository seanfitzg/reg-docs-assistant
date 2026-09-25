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
# Deliberately not called a "hit": in CONTEXT.md that word means a
# retrieved Chunk matching a Gold Locator under ADR-0028's rule, which a
# keyword result is not.
@dataclass(frozen=True)
class KeywordMatch:
    document_id: str
    locator: str
    snippet: str


def search(chunks: list[dict], terms: str, document_id: str | None = None) -> list[KeywordMatch]:
    """Chunks containing every whitespace-separated term, case-insensitively.

    Terms are ANDed rather than matched as one phrase, because PDF
    extraction leaves line breaks and double spaces mid-sentence -- an exact
    phrase would miss "comprehensive\\nconsumer".
    """
    # .split() with no argument splits on any run of whitespace and drops
    # empty strings; .lower() makes the comparison case-insensitive.
    wanted = [t.lower() for t in terms.split()]

    # Blank terms must be rejected explicitly: all() over an empty sequence
    # is True ("vacuous truth" -- no item failed), so without this every
    # Chunk would match and wanted[0] below would raise IndexError. An empty
    # list is falsy in Python, so "not wanted" means "wanted is empty".
    if not wanted:
        raise ValueError("search needs at least one search term")

    matches = []
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
            matches.append(KeywordMatch(chunk["document_id"], chunk["locator"], snippet))
    return matches


# argv is a parameter (defaulting to None, which argparse reads as "use the
# real command line") so tests can call main([...]) with their own
# arguments -- the same seam as injecting string[] args into a C# Main.
# "list[str] | None" is a type hint meaning "a list of strings, or None" --
# like a nullable reference type, string[]?.
def main(argv: list[str] | None = None) -> int:
    # argparse builds a command-line parser from declarations, and prints
    # --help and usage errors for free -- similar to System.CommandLine.
    parser = argparse.ArgumentParser(description="Find (document_id, locator) pairs by keyword.")
    parser.add_argument("terms", help="words that must all appear in the Chunk text")
    parser.add_argument("--doc", help="only search this document_id")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR, help="ingestion output to search")
    args = parser.parse_args(argv)

    # parser.error() prints the usage line plus the message to stderr and
    # exits with status 2 -- the same way argparse reports its own errors,
    # instead of letting search()'s ValueError surface as a traceback.
    if not args.terms.split():
        parser.error("terms must contain at least one word")

    # On Windows, output piped or redirected (not a live console) defaults to
    # the legacy cp1252 code page, so curly quotes and bullets from the PDFs
    # arrive as mojibake in a UTF-8 terminal -- bad when this output is where
    # answer_quote text gets copied from. Force UTF-8 regardless.
    sys.stdout.reconfigure(encoding="utf-8")

    if not (args.output_dir / "chunks").is_dir():
        # file=sys.stderr sends this line to the error stream rather than
        # stdout -- Console.Error.WriteLine rather than Console.WriteLine.
        print(f"No ingestion output at {args.output_dir} -- run the ingestion pipeline first.", file=sys.stderr)
        return 1

    chunks = load_active_chunks(args.output_dir)

    # A mistyped --doc would otherwise just print "0 match(es)", which reads
    # like "not in this Document" -- say plainly that the id doesn't exist.
    # any(...) is LINQ's .Any().
    if args.doc is not None and not any(c["document_id"] == args.doc for c in chunks):
        print(f"No Document with id {args.doc!r} in {args.output_dir}.", file=sys.stderr)
        return 1

    matches = search(chunks, args.terms, args.doc)
    for match in matches:
        print(f"{match.document_id}  |  {match.locator}")
        print(f"    ...{match.snippet}...")
    print(f"{len(matches)} match(es)")
    return 0


# True only when this file is run directly ("python eval/find_locator.py"),
# not when a test imports it -- the usual guard, as in store/loader.py.
if __name__ == "__main__":
    sys.exit(main())
