# The chat provider is chosen at startup by `LLM_PROVIDER`; embeddings stay on local Ollama

`LLM_PROVIDER` (`ollama`, the default, or `openai`) picks which chat model backs all three model Steps: the injection classifier in classify, the drafter, and the verify judge. It is read once when the app is built, so switching means a restart. `JUDGE_MODEL` still overrides the judge's model name, and must name a model the chosen provider serves. `models.py` holds the factory, each provider's default model, and the cost calculation.

Embeddings are not part of the switch. A stored vector is only comparable to a query vector from the same model and size (ADR-0026), and `chunk_embeddings` is `vector(768)` for `nomic-embed-text`. OpenAI's embedding models are a different size and a different space, so using them means a new table or column, re-embedding every Chunk, and a fresh eval baseline (ADR-0030). That is a retrieval change to be measured on its own, not something to slip in beside a chat-model swap. The result is a hybrid: retrieval runs locally and only the question and the retrieved Chunks go to OpenAI.

Two alternatives were weighed:

- **Switching per request.** Useful for side-by-side comparison, but the Event records the model name per Step and the app would need to hold both clients and decide which a request gets. A startup switch is enough to run the eval set once per provider.
- **Hard-swapping to OpenAI.** Simpler, but loses the free local path for development and tests, and the baseline the prompts were tuned against.

Cost is now real. Steps used to record `cost: 0` unconditionally; a paid model's Step records the dollars its token usage cost, from a price table in `models.py` kept by hand (the openai provider refuses to start with a model that has no price, so a paid Step never records 0 by accident; local models cost 0). The table can go stale, so a total is an estimate until checked against OpenAI's own usage page.

Provider failures (Ollama aborting a run, OpenAI refusing a key or running out of credit) surface from `POST /query` as a 502, as Ollama's already did. verify's tolerance for a judge aborted by Ollama (the "token repeat limit" loop) is unchanged and Ollama-specific: an OpenAI error in the judge fails the request rather than quietly leaving the answer unverified, because an exhausted quota should be visible, not look like a low-confidence answer.

Prompts and thresholds were tuned against `qwen2.5:7b-instruct`. The first OpenAI run is a new baseline, not a comparison with the Ollama one.
