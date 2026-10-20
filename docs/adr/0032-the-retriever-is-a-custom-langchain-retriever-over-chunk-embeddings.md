# The retriever is a custom LangChain retriever over `chunk_embeddings`, not LangChain's PGVector

Track B's retriever subclasses LangChain's base retriever and runs the existing similarity-search SQL (the query in `eval/run_eval.py`) against `chunk_embeddings`, reusing `store/db.py` and the embedding client. Each result becomes a LangChain `Document` whose metadata carries the Chunk id, document id, locator and score, which is exactly what an Event's `retrieve` Step records.

LangChain's ready-made `PGVector` integration was rejected. It creates and manages its own tables with its own column layout, so using it would mean either duplicating every embedding into a second table or bending `/store` to fit it. That would conflict with ADR-0024 (embeddings keyed by Chunk and model), ADR-0025 (only active-generation Chunks are candidates) and ADR-0022 (typed columns). It would also hide the search SQL, which is the part worth understanding.

The first version is pure vector search and must reproduce the baseline run report's numbers (ADR-0030). Hybrid keyword-plus-vector search is a later, separately measured change, so a difference from the baseline can only mean a porting bug, not a changed algorithm.

Anything downstream sees only LangChain's retriever interface, so swapping in a hybrid retriever later changes one class.
