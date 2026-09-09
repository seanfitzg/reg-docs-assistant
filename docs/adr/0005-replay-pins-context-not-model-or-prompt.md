# Replay pins retrieved context; model and prompt version stay current

When Replay re-executes a query's pipeline, only the retrieved chunk text is pinned to what the original `Event` recorded. The model and prompt version used are whatever's currently active in production, not the ones that originally answered the query.

The alternative — pinning model and prompt too — would only test raw LLM non-determinism given identical everything, which is a narrower and less useful check. Pinning context only means Replay also surfaces drift after a prompt change or model swap: "would today's pipeline still reach the same conclusion from yesterday's evidence?" This is what makes Replay usable for the local-model-vs-Claude comparison the eval harness needs, and for catching regressions after a prompt version bump.
