# Eval Cases are hand-written and tagged by phrasing and category

Every Eval Case is written by the owner, not generated or drafted by an LLM, and carries two tags that the eval report breaks its metrics down by:

- **`phrasing: lexical | paraphrase`** — roughly half each. `lexical` questions reuse the source passage's own vocabulary; `paraphrase` questions deliberately ask it the way a consumer or compliance analyst would, avoiding the passage's key terms.
- **`category`** — `single_passage` (the bulk, ~12–14, spread across both chunking strategies and most Documents), `multi_locator` (2–3), `supersession` (2: Gold Locator is the newer Document's, the superseded Document's equivalent recorded separately), and `unanswerable` (2–3: questions the corpus genuinely can't answer).

The phrasing tag exists because of *lexical overlap bias*: a question written while looking at a passage tends to echo its wording, and embedding (and especially keyword) retrieval scores that echo highly — so an eval made only of such questions overstates how well retrieval will do for real users, who don't know the Document's wording. Rather than trying to eliminate the bias, tagging it turns it into a measurement: the gap between lexical and paraphrase recall shows how much the embedding model understands meaning versus matching words.

LLM-drafted cases were rejected for the same reason: they echo source wording even more strongly than hand-written ones, and the eval set would stop being the owner's own judgement of what matters. Tooling may still help with the mechanical part (finding the right locator); the questions, tags and gold labels are human decisions.

`unanswerable` cases are excluded from Recall@k and MRR — plain top-k retrieval always returns k Chunks, so recall is meaningless for them. They exist to supply the similarity-score data a future `no_chunks_retrieved` threshold will be tuned against (ADR-0030).
