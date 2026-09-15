# Ingestion is a single shared pipeline, not duplicated per track

Turning corpus PDFs into `Document` and `Chunk` records is implemented once (Python), not built separately in each of the .NET/Python tracks. Both tracks read the same ingested `Document`/`Chunk` records, mirroring the shared audit-event table.

The rest of this project deliberately proves stack-portability by building the same thing twice (Track A .NET, Track B Python). Ingestion doesn't need to carry that story: PDF parsing and chunking aren't RAG, agent-orchestration, or model-integration work, so duplicating them teaches nothing new about either stack. Duplicating it would also risk the two tracks silently landing on different Chunks for the same Document, which would make any retrieval-quality comparison between them meaningless. The portability proof is already fully carried by the shared event schema, shared corpus, and shared eval set.
