# /schema

JSON Schema definitions for RegDocs Assistant's shared domain model (`Event`, `Document`, `Chunk`, and related shapes — see `CONTEXT.md` and `docs/adr/`), validated against fixture payloads by a Python test harness.

This directory is a shared contract both Track A (.NET) and Track B (Python) implementations validate against. The schema and fixture files themselves are plain JSON — only the test harness that validates them is Python (a deliberate learning choice, see `docs/adr/0011-schema-validation-harness-is-python.md`).

## Setup

```
python -m venv schema/.venv
schema/.venv/Scripts/activate      # Windows
# source schema/.venv/bin/activate # macOS/Linux
pip install -r schema/requirements.txt
```

## Running the tests

```
python -m pytest schema/tests
```

Exit code `0` means every fixture validated as expected; a non-zero exit code means at least one didn't.

On Windows machines with an Application Control policy (WDAC/AppLocker), running `pytest.exe` directly can be blocked since pip-installed console-script `.exe` wrappers are typically unsigned. `python -m pytest` runs the same code through the signed `python.exe` interpreter instead, avoiding the block — use this form rather than the bare `pytest` command.

## Layout

- `<name>.schema.json` at the top level — one JSON Schema per domain concept (`document.schema.json`, `chunk.schema.json`, `event.schema.json`, `event-flagged.schema.json`, `answer-overridden.schema.json`).
- `fixtures/<name>/` — example payloads for that schema, named for what they demonstrate (e.g. `valid-original.json`, `invalid-missing-required.json`) and asserted to pass or fail validation accordingly.
- `tests/` — one pytest file per group of *related* schemas, not strictly one per schema name: `test_document_chunk.py` covers `document.schema.json` and `chunk.schema.json` together, `test_event.py` covers `event.schema.json`, `event-flagged.schema.json`, and `answer-overridden.schema.json` together — because within each group the schemas share fixtures and cross-schema relationship assertions (a `Document` that `supersedes` another; an `EventFlagged`/`AnswerOverridden` that references a real `Event` by id) that don't belong to any one schema alone. Split into per-schema files instead once schemas in a group stop sharing that kind of relationship test.
- `tests/support.py` — shared test helpers (`load_json`, and `validate`, which enforces JSON Schema `format` constraints that `jsonschema.validate()` skips by default unless told to check them). Every new test file should validate through `support.validate()`, not call `jsonschema.validate()` directly, so format enforcement is never silently opted out of. The one exception is `test_harness.py` itself, which predates `support.py` and stays hand-annotated in its original form as a line-by-line Python primer — its trivial schema has no `format` constraints to enforce, so nothing is actually lost by it not using the shared helpers.

`fixtures/trivial/` (with its schema alongside it, not at the top level) is a throwaway example proving the harness itself works end-to-end; it's not part of the real domain model.
