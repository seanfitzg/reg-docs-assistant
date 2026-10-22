# Python code is a uv workspace of `src/`-layout packages, not folders sharing `sys.path`

The five Python folders (`schema`, `ingestion`, `store`, `eval`, `track-b`) are members of one uv workspace with a single root `.venv` and `uv.lock`. Each is an installable package under `src/` with a `regdocs_` prefix (`regdocs_store`, `regdocs_eval`, and so on), and a folder that uses another declares it as a dependency in its own `pyproject.toml` (`track-b` depends on `regdocs-store`). One `pytest` run from the repo root covers every folder.

This replaces five per-folder venvs and `requirements.txt` files, and the `sys.path.insert` edits in modules and `conftest.py` files that let one folder import another's flat modules (`from db import ...`). Those edits hid real dependencies, depended on import order, and made same-named modules from different folders collide, which is why the suites couldn't run in one session.

Shared test helpers live in a `testing` module in the owning package (`regdocs_store.testing`, `regdocs_schema.testing`, `regdocs_track_b.testing`), so a cross-folder test import is an ordinary declared dependency. A shared `regdocs-testing` package would risk dependency cycles; fixtures in a root `conftest.py` would not cover plain helper functions.

Data files stay where they are (`schema/*.json`, `eval/dataset.json`, `ingestion/manifest.json`, `track-b/prompts`), and the code finds them from the repo root. The schema is the contract Track A reads by path, and nothing here is built into a wheel, so package data would add moves without benefit. The packages are therefore only meant to run from a repo checkout.

`ingestion/ids.py` is still duplicated in `store/loader.py` (ADR-0023). Packaging makes importing it possible, but doing so would either pull ingestion's PDF dependency into `store` or move `ids` into `regdocs_schema`, which is a separate decision.
