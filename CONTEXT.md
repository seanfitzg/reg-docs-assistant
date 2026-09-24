# RegDocs Assistant

A RAG and multi-step agent system that answers questions about Irish financial-regulation documents, where every answer is backed by an immutable, replayable audit trail.

## Language

### Audit & events

**Event**:
An immutable, append-only record of one user-facing query and its full answer, including the nested trace of pipeline steps that produced it. Never edited after being written — a correction is a new Event, not a change to an existing one.
_Avoid_: Log entry, record, interaction

**Step**:
One stage of the multi-step agent pipeline (classify, retrieve, draft, verify — in that order) nested inside a query's Event, each carrying its own model, cost, and latency. Each Step runs exactly once per query; verify annotates the draft with Confidence and Flags, it never triggers a retry or re-draft.

**Replay**:
Re-executing a query's pipeline against its pinned retrieved context (the same chunk text, not just chunk ids) to produce a fresh answer, for comparison against the originally stored answer. Only the context is pinned — Replay runs the *current* model and prompt version, not the ones that originally answered, so it surfaces drift from pipeline changes as well as ordinary model non-determinism. A replay producing different *wording* is expected and not itself a problem. What matters is whether the substance changed.
_Avoid_: Review, playback — those describe viewing a stored Event, not re-executing it

**Agreement Check**:
The process of deciding whether a Replay's answer still agrees with the original: first compare extracted structured facts (e.g. the regulation section cited) between the two, since this is free and instant; only if that's inconclusive, escalate to a second AI call that judges semantic agreement directly.
_Avoid_: Match, verification — verification already names the pipeline's own verify Step, a different concept

**Override**:
A human correction to a query's answer, captured as its own new `AnswerOverridden` Event that references the original `QueryAnswered` Event by id. The original Event is never modified.
_Avoid_: Edit, correction — both imply changing the original record in place

**Confidence**:
A score computed by the verify Step, measuring how well the retrieved context supports the drafted answer — never the model's self-reported certainty, which is unreliably calibrated. A high score is a signal, not a guarantee: retrieved context can genuinely support an answer that's still wrong (e.g. superseded by an amendment the retrieval step didn't pull in), which is what Override exists for.
_Avoid_: Certainty — implies self-assessment, which this deliberately is not

**Flag**:
A marker from a closed vocabulary, attached to an Event to signal a concern requiring attention: `low_confidence`, `no_supporting_context`, `no_chunks_retrieved`, `pii_detected`, `possible_prompt_injection`, `possibly_superseded_source`, `human_flagged`. Automated flags (all but the last) are known at write time and stored on the original Event, each produced by a specific Step: `classify` produces `pii_detected` and `possible_prompt_injection` (both judgments about the raw incoming query), `retrieve` produces `possibly_superseded_source` and `no_chunks_retrieved`, `verify` produces `low_confidence` and `no_supporting_context` (this one specifically means the drafted answer strayed beyond what retrieved Chunks support — not that nothing was retrieved; see `no_chunks_retrieved` for that case). Most automated flags are annotate-only — the pipeline runs to completion regardless. Two exceptions halt the pipeline instead, skipping every downstream Step since there's nothing left for them to usefully do: `possible_prompt_injection` at `classify`, and `no_chunks_retrieved` at `retrieve`. A human raising `human_flagged` after the fact creates a new `EventFlagged` Event referencing the original — same rule as Override, never a mutation.
_Avoid_: Warning, alert — too generic, don't imply the closed vocabulary

**Redaction**:
Removing PII from a query or answer before an Event is persisted, triggered by `classify`'s `pii_detected` flag. Redaction doesn't stop the pipeline — `retrieve`/`draft`/`verify` still run normally against the original text; only what gets written to storage is affected.
_Avoid_: Scrubbing, masking — Redaction is this project's specific term for the pre-persistence step

**Citation**:
A resolved locator (e.g. a section number) attached to a claim in a drafted answer, produced by a deterministic lookup against the Chunk `draft` referenced by marker — never text the model generates itself. Guarantees every Citation shown corresponds to a Chunk that was genuinely retrieved for that query.
_Avoid_: Reference, source — fine as loose synonyms in prose, but Citation is this project's term for the resolved, verified form specifically

### Documents & retrieval

**Document**:
An immutable record of one point-in-time regulatory publication (e.g. one PDF as issued by the Central Bank of Ireland or CCPC). Never edited after ingestion — a regulatory amendment is a new Document, not a change to an existing one.
_Avoid_: File, PDF, page — those name the artifact, not the domain concept

**Supersedes**:
A link recorded on a new Document at ingestion, pointing back to the earlier Document it replaces. Marks the earlier Document — and any Chunk retrieved from it — as a candidate for the `possibly_superseded_source` flag.
_Avoid_: Replaces, version of — a Document is not modeled as a version of some longer-lived entity; each is independent, connected only by this link

**Chunk**:
An immutable retrieval and citation unit derived from a Document, aligned to the Document's own structure (a clause or numbered section) rather than a fixed-size token window. Reprocessing a Document with a new chunking strategy produces a fresh set of Chunks — existing ones are never overwritten. Its locator directly names searchable structure (a clause number) where the Document has one; where it doesn't — narrative Documents with only free-text headings — the locator instead pairs the heading with the page it starts on, since a heading alone is neither unique nor locatable in a long Document.
_Avoid_: Passage, segment, window — "window" in particular implies fixed-size chunking, which this project deliberately avoids

**Chunking Generation**:
The full set of Chunks produced by one run of a chunking strategy over a Document. A Document tracks which Generation is active via `active_chunking_generation_id`; only the active Generation's Chunks are eligible for retrieval, though earlier Generations stay in storage to satisfy Replay.
_Avoid_: Version — reserved for Document supersession, a different kind of "old vs new"; conflating the two would blur a regulatory amendment with a re-chunking run

**Chunk Embedding**:
A vector representation of one Chunk's text, produced by a specific embedding model, used to find candidate Chunks for a query via nearest-neighbor similarity search. Keyed by (Chunk, embedding model) — trying a different model produces additional Chunk Embeddings alongside existing ones, never replacing them, the same "old stays, new is additive" shape as Chunking Generation. Only computed for Chunks belonging to a Document's active Chunking Generation, since an inactive Generation's Chunks are never retrieval candidates in the first place.
_Avoid_: Vector, embedding (bare) — "Chunk Embedding" is this project's term for the persisted, model-keyed form specifically

### Evaluation

**Eval Case**:
One hand-written question in the retrieval eval set, with its Gold Locators, a verbatim answer quote for human sanity-checking, and `phrasing` and `category` tags. Measures whether retrieval surfaces the right source; says nothing about the quality of a drafted answer.
_Avoid_: Test case, sample, Q&A pair — "Eval Case" is the project's term for this labelled retrieval check specifically

**Gold Locator**:
A `(document_id, locator)` pair naming where the correct answer to an Eval Case lives in the source Document's own structure — deliberately not a Chunk id, so it survives re-chunking. A retrieved Chunk is a hit if its locator matches any of the case's Gold Locators under the eval's deterministic match rule (segment-aware for clause numbers; exact heading and page within ±1 for heading-section Documents).
_Avoid_: Ground truth, expected chunk — a Gold Locator never names a Chunk
