# Schema-validation harness is written in Python

The `/schema` validation harness (tickets #2–#4: the trivial-schema proof, the `Document`/`Chunk` fixtures, and the `Event`/`Step`/`Flag` fixtures) is implemented in Python, rather than a more conventional choice for pure JSON Schema tooling like Node.js.

The reason is explicitly a learning one, not a technical one: this project exists so the owner can learn AI/ML, and Python — the language Track B (FastAPI, LangChain, LangGraph) will use — has zero presence on their CV. A small, self-contained, low-stakes tooling piece like this is a reasonable place to start building Python fluency before Track B proper begins. This is **not** a signal that Track B is being built ahead of Track A, or that Track A is deprioritized: the `/schema` JSON Schema files and fixture payloads themselves remain fully language-agnostic and are consumed identically by both tracks — only the test harness that validates them is Python.
