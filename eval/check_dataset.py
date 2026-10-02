# Relational checks on eval/dataset.json that its JSON Schema
# (schema/eval-dataset.schema.json) can't express: unique case ids, and
# Gold Locators that genuinely exist among the active Chunks.
#
# The locator check is deliberately EXACT string equality. It answers "is
# this label a typo?", not "would retrieval count this as a hit?" -- that's
# the structure-aware match rule (ADR-0028), a separate concern. A typo'd
# label would otherwise look exactly like a retrieval miss on every run.


def find_problems(dataset: dict, active_chunks: list[dict]) -> list[str]:
    """Human-readable problems with the dataset; an empty list means none."""
    problems = []

    # Every (document_id, locator) pair that actually exists. A set of
    # tuples gives O(1) membership checks below, like a HashSet<(string,
    # string)> in C# -- tuples compare by value, so ("a", "1.1") == ("a",
    # "1.1") even when they're different objects.
    existing = {(c["document_id"], c["locator"]) for c in active_chunks}

    seen_ids = set()
    for case in dataset["cases"]:
        case_id = case["id"]
        if case_id in seen_ids:
            # An f-string: f"...{expr}..." interpolates expressions inline,
            # the same as C#'s $"...{expr}..." interpolated strings.
            problems.append(f"duplicate case id: {case_id}")
        seen_ids.add(case_id)

        # Both lists are checked the same way; the label differs only so
        # the message says which list the bad entry is in. Each item of the
        # tuple-of-tuples is a (field, label) pair, and "for field, label
        # in ..." unpacks it into two variables per iteration -- like a C#
        # foreach (var (field, label) in ...) over value tuples.
        # superseded_locators is optional, so .get(..., []) falls back to an
        # empty list rather than raising KeyError when it's absent.
        for field, label in (("gold_locators", "gold"), ("superseded_locators", "superseded")):
            for entry in case.get(field, []):
                if (entry["document_id"], entry["locator"]) not in existing:
                    problems.append(
                        f"{case_id}: {label} locator not found in active Chunks: "
                        f"{entry['document_id']} / {entry['locator']}"
                    )

    return problems
