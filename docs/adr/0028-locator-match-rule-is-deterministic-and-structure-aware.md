# The eval's locator match rule is deterministic and structure-aware

Whether a retrieved Chunk counts as a hit for a Gold Locator (ADR-0027) is decided by a pure, hand-written function of the two locator strings and the Document's chunking strategy — no fuzzy string matching, no embedding similarity, no LLM judge. The rule:

- **Clause-numbered Documents:** compare by numbering *segment*, not raw string prefix. Gold `3.12` matches retrieved `3.12` and a child like `3.12(a)`, but gold `3.1` does **not** match `3.12` — the naive `startswith` bug this rule exists to prevent.
- **Heading-section Documents:** the heading must match exactly, and the page may differ by at most ±1. The page is kept (not ignored) because it is what disambiguates repeated headings like "Introduction" within one Document — the reason ADR-0015 added it to the locator in the first place.
- **Multiple Gold Locators per case:** a case is a hit if *any* of its Gold Locators matches a retrieved Chunk. A stricter "all must be retrieved" recall is deferred until multi-hop questions need it.

Determinism is the point: the eval measures the retriever, and a grader with its own variance would make it impossible to tell a retrieval change from grader noise. Exact string equality was the simpler alternative and is correct against today's chunkers, but it would score a finer or differently-paginated chunker as a miss even when it retrieved the right text — throwing away the re-chunking robustness ADR-0027 was chosen for.

Deliberately not handled: a coarser chunker merging two clauses into one Chunk. That Chunk carries a single locator string (e.g. `3.11`), so nothing in the data says it also covers `3.12`; detecting it would need range locators from the chunker. That is a schema question for when such a chunker exists, not something the grader should guess at.
