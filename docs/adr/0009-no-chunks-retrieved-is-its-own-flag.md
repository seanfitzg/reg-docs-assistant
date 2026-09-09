# no_chunks_retrieved is its own flag, separate from no_supporting_context

Two different failure modes were at risk of collapsing into one flag. `retrieve` finding zero Chunks above the similarity threshold (nothing in the corpus is relevant to the query) and `verify` judging a drafted answer as unsupported by the Chunks it did retrieve are different problems, so they get different flags:

- **`no_chunks_retrieved`** — produced by `retrieve` when nothing clears the threshold. Halts the pipeline immediately, the same way `possible_prompt_injection` does (ADR-0008): `draft` and `verify` are skipped, since there's no context for `draft` to usefully work from. The `Event` is written with only `classify`+`retrieve` Steps present, and the user gets a "couldn't find relevant information" response.
- **`no_supporting_context`** — produced by `verify`, unchanged from its original meaning: the drafted answer strayed beyond what the retrieved Chunks actually support, even though some Chunks were found. Annotate-only, per ADR-0006 — the answer is still returned, just flagged.

Splitting them means the flag itself tells you which situation occurred without needing to inspect the Event's Step trace, and it keeps `no_supporting_context`'s meaning precise now that `Confidence`'s definition already presupposes both a retrieved context and a drafted answer exist.
