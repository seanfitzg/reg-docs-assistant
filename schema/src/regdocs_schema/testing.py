# Shared helpers for the schema tests, so each test_<name>.py doesn't
# re-define its own copy.
import json
from pathlib import Path

import jsonschema

# jsonschema.validate() treats a schema's "format" keyword (e.g. "date",
# "uri") as advisory unless a FormatChecker is passed in explicitly -- a
# deliberate library design choice. Every schema test should go through
# validate() below rather than jsonschema.validate() directly, so format
# constraints are never silently skipped by a file that forgot to opt in.
FORMAT_CHECKER = jsonschema.FormatChecker()


def load_json(path: Path):
    return json.loads(path.read_text())


def validate(payload, schema):
    jsonschema.validate(instance=payload, schema=schema, format_checker=FORMAT_CHECKER)
