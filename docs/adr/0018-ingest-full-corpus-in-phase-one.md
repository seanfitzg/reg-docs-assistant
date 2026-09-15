# Ingest the full 20-document corpus in phase one, not just the Consultation Papers

Phase one ingestion targets all 20 corpus documents, not a narrower first pass limited to the 10 clause-numbered Consultation Papers.

The corpus splits unevenly in ingestion difficulty: the CPs are clean and clause-numbered, while the other 10 are narrative documents needing the `heading_sections`/`academic_sections` strategies plus document-specific cleanup flags (ADR-0014, ADR-0016). But every mechanism designed this session — manifest-driven metadata, per-document strategy, per-document cleanup flags — exists specifically to make that heterogeneity tractable, and this session's fact-finding already worked out a concrete plan for every document category in the corpus. Deferring the narrative half wouldn't avoid unresolved design risk; it would just move already-solved work past the point where gaps would otherwise surface early.
