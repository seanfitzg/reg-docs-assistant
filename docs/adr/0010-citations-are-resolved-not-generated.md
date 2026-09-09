# Citations are resolved by lookup, never written by the model

`draft` never writes citation text itself. It marks which retrieved Chunks support each claim using a simple numbered marker (e.g. `[1]`, `[2]`) tied to the list of Chunks it was given. A separate, deterministic post-processing step then resolves each marker to that Chunk's actual stored locator (its section number) before the answer is shown or persisted.

The alternative — letting the model write the section number as free text — was rejected because LLMs are unreliable at reproducing exact identifiers from memory, and a plausible-but-wrong citation is a worse failure mode for a compliance tool than an obviously missing one. Resolving markers by lookup instead of generation guarantees every Citation the user sees corresponds to a Chunk that was genuinely retrieved for that query — a database fact, not a model claim.
