# Eval runs are immutable, committed reports that pin their configuration

Every run of the retrieval eval harness writes a new JSON report to `eval/runs/<timestamp>-<model>.json`, committed to the repo and never overwritten. Each report records:

- **Configuration:** embedding model, the active Chunking Generation of every Document at run time, the eval set's `dataset_version`, k, and the query prefix.
- **Summary metrics:** Recall@1/3/5/10 and MRR — overall, by `phrasing`, and by `category` (ADR-0029), all computed from a single top-10 retrieval per case.
- **One line per Eval Case:** the rank at which a Gold Locator was matched (or a miss); the similarity score at the gold Chunk for answerable cases, and the top similarity score for `unanswerable` cases.

A retrieval score is meaningless without what produced it: change the embedding model, a Document's chunking, the eval set, or k and the number moves. Without pinned configuration, later comparisons — a new chunker, a different embedding model, the Week-7 local-vs-Claude comparison — rest on memory. This is the same principle as Replay pinning its context (ADR-0005), applied to evaluation rather than answering; and append-only reports mirror the append-only Event store.

Console-only output was rejected as unrepeatable; a Postgres table was rejected as extra schema for no query need, invisible on GitHub, and lost on a Docker-volume reset. The per-case lines matter as much as the summary: they're what makes a miss investigable ("why did q07 rank 14th?"). The score fields are the first evidence for whether a similarity threshold can separate answerable from unanswerable questions at all with this model — if the two distributions overlap heavily, that is a finding, not a failure.
