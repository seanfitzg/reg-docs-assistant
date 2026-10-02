# The Gold Locator match rule (ADR-0028): decides whether a retrieved
# Chunk's locator counts as a hit for a Gold Locator. Pure functions, no
# I/O -- the harness (#32) supplies each retrieved Chunk's
# chunking_strategy from /store.
#
# Deliberately deterministic: no fuzzy matching, similarity or LLM judge.
# The eval measures the retriever, and a grader with its own variance would
# make a retrieval change indistinguishable from grader noise.
#
# Anything this rule can't parse RAISES rather than returning False. A
# silent False would be scored as a retrieval miss, which is exactly the
# kind of wrong-but-plausible number an eval must never produce.

import re

# A clause locator: a dotted number, optionally followed by parenthesised
# sub-parts -- "3", "3.12", "3.12(a)", "3.12(a)(i)". Today's clause_numbered
# chunker only emits "N.N", but a finer chunker could emit children, and
# ADR-0028's rule is defined over them.
#
#   [0-9]+              the first number ("3"). [0-9] rather than \d,
#                       because Python's \d also matches non-ASCII digits
#                       like Arabic-Indic "٣" -- this must stay strict.
#   (?:\.[0-9]+)*       then any number of ".digits" ("." "12"). (?:...) is
#                       a NON-capturing group: it groups for the * without
#                       creating a numbered capture, since nothing reads it.
#   (?:\([A-Za-z0-9]+\))*   then any number of "(a)", "(i)", "(2)" parts;
#                       \( and \) are escaped literal brackets.
CLAUSE_PATTERN = re.compile(r"[0-9]+(?:\.[0-9]+)*(?:\([A-Za-z0-9]+\))*")

# Splits a clause locator (already validated by CLAUSE_PATTERN) into its
# segments: "3.12(a)" -> ["3", "12", "(a)"]. The brackets are kept on
# sub-parts so "3.1.2" (["3", "1", "2"]) and "3.1(2)" (["3", "1", "(2)"])
# stay different. The "|" means "or": a run of digits, or a whole (...) part.
CLAUSE_SEGMENT = re.compile(r"[0-9]+|\([A-Za-z0-9]+\)")

# A heading locator (ADR-0015): "<heading> (p. <n>)". Used by both
# heading_sections and academic_sections -- every active locator either
# strategy currently emits parses with it.
#
#   (.+)        the heading, captured as group 1: one or more of any
#               character, so headings with their own brackets and digits
#               ("(4)", "Figure 1: ...") pass through untouched.
#   " \(p\. "   a literal space, "(p." and a space; \( and \. escape the
#               bracket and dot, which are otherwise regex syntax.
#   ([0-9]+)\)  the page digits (ASCII only, as above), captured as
#               group 2, then ")".
#
# It's always used with fullmatch (see _parse_heading), which pins the
# "(p. N)" part to the very END of the string -- so if a heading ever
# contained its own "(p. N)", the page would still be the last one.
HEADING_PATTERN = re.compile(r"(.+) \(p\. ([0-9]+)\)")

# How far apart two pages may be and still be the same section. Enough to
# absorb a chunker that paginates differently; not so much that a repeated
# heading a couple of pages on (a second "Introduction") gets conflated.
PAGE_TOLERANCE = 1


def _clause_segments(locator: str) -> list[str]:
    # fullmatch (not match or search) requires the WHOLE string to fit the
    # pattern -- like anchoring a C# Regex with \A...\z. Without it, "3.12."
    # would pass because its "3.12" prefix fits.
    if not CLAUSE_PATTERN.fullmatch(locator):
        # {locator!r} formats the value with repr() rather than str(), so
        # it prints quoted -- 'Introduction' -- and an empty or
        # whitespace-only locator is visible in the message, not blank.
        raise ValueError(f"unparseable clause_numbered locator: {locator!r}")
    return CLAUSE_SEGMENT.findall(locator)


def _clause_covers(gold_segments: list[str], retrieved_segments: list[str]) -> bool:
    # The retrieved clause is inside the gold one when the gold's segments
    # are a prefix of the retrieved's: ["3", "12"] is a prefix of
    # ["3", "12", "(a)"], but ["3", "1"] is NOT a prefix of ["3", "12"],
    # because "1" != "12" as whole segments. That's the whole difference
    # from a naive retrieved.startswith(gold) string check, which would say
    # "3.12".startswith("3.1") -- True -- and wrongly score 3.12 as a hit
    # for gold 3.1.
    #
    # retrieved_segments[:n] slices the first n items (a shorter list just
    # yields what it has), and == on lists compares element by element --
    # like LINQ's .Take(n).SequenceEqual(...).
    return retrieved_segments[: len(gold_segments)] == gold_segments


def _parse_heading(locator: str) -> tuple[str, int]:
    match = HEADING_PATTERN.fullmatch(locator)
    if match is None:
        raise ValueError(
            f"unparseable heading_sections/academic_sections locator: {locator!r}"
        )
    # A tuple return -- like C#'s (string Heading, int Page) value tuple.
    # int(...) converts the captured digits, since regex groups are strings.
    return match.group(1), int(match.group(2))


def _heading_covers(gold: tuple[str, int], retrieved: tuple[str, int]) -> bool:
    # Tuple unpacking: assigns a tuple's two values to two names at once,
    # like C#'s var (heading, page) = gold.
    gold_heading, gold_page = gold
    retrieved_heading, retrieved_page = retrieved
    # Exact heading equality, whitespace and case included: both sides come
    # from the same Document's extraction, so normalising would only risk
    # merging two genuinely different headings.
    return (
        gold_heading == retrieved_heading
        and abs(gold_page - retrieved_page) <= PAGE_TOLERANCE
    )


# chunking_strategy -> (parse, covers) for that strategy's locator format:
# parse turns a locator string into something comparable (raising if it
# can't), and covers compares a parsed gold with a parsed retrieved
# locator. Keeping them separate lets case_hit parse every retrieved Chunk
# up front, before any comparison. A dict of functions is Python's everyday
# stand-in for a switch expression or a Dictionary<string, (Func<...>,
# Func<...>)>: functions are ordinary values, stored like any other.
RULES = {
    "clause_numbered": (_clause_segments, _clause_covers),
    "heading_sections": (_parse_heading, _heading_covers),
    "academic_sections": (_parse_heading, _heading_covers),
}


def _rule(chunking_strategy: str):
    # .get() returns None for a missing key instead of raising KeyError --
    # like TryGetValue -- so the error below can name the bad strategy.
    rule = RULES.get(chunking_strategy)
    if rule is None:
        raise ValueError(f"unknown chunking strategy: {chunking_strategy!r}")
    return rule


def locator_matches(
    gold_locator: str, retrieved_locator: str, chunking_strategy: str
) -> bool:
    """Whether a retrieved Chunk's locator is a hit for a Gold Locator.

    Both locators must belong to the same Document -- that's the caller's
    check (case_hit does it) -- so one chunking_strategy governs both.
    Raises ValueError for an unknown strategy or an unparseable locator.
    """
    # Unpacks the (parse, covers) pair from RULES into two local names.
    parse, covers = _rule(chunking_strategy)
    return covers(parse(gold_locator), parse(retrieved_locator))


def case_hit(gold_locators: list[dict], retrieved: list[dict]) -> bool:
    """Whether any of an Eval Case's Gold Locators matches any retrieved Chunk.

    gold_locators are the case's {"document_id", "locator"} entries;
    retrieved are {"document_id", "locator", "chunking_strategy"} dicts, as
    the harness's retrieval query returns them. A locator only ever matches
    within its own Document, and an empty gold_locators is never a hit.

    Every retrieved Chunk is checked (known strategy, parseable locator),
    whatever its Document. A gold locator is only parsed against a
    retrieved Chunk from its own Document, since that's where its strategy
    comes from -- so a malformed gold whose Document wasn't retrieved isn't
    caught here. test_dataset.py's exact-existence check covers that: a
    gold that exists among the real Chunks is parseable by construction.
    """
    # Parse every retrieved Chunk first, so bad retrieval data raises even
    # when no gold shares its Document. Found in review: without this, an
    # unknown strategy on another Document's Chunk silently scored a miss.
    for chunk in retrieved:
        parse, _ = _rule(chunk["chunking_strategy"])
        parse(chunk["locator"])

    # A generator expression with two "for" clauses loops over every
    # (gold, chunk) pair -- like a nested foreach, or LINQ's SelectMany.
    # The "if" skips pairs from different Documents before comparing: a
    # locator only means something within its own Document. any() stops at
    # the first True (like .Any()), and is False for an empty sequence.
    return any(
        locator_matches(gold["locator"], chunk["locator"], chunk["chunking_strategy"])
        for gold in gold_locators
        for chunk in retrieved
        if gold["document_id"] == chunk["document_id"]
    )
