# Shared helpers for the schema tests, so each test_<name>.py file doesn't
# re-define its own copy (pytest auto-adds this directory to the import
# path, which is why "from support import ..." resolves without a package
# setup, similar to how a .NET test project resolves a sibling class file).
import json
from pathlib import Path

import jsonschema

# jsonschema.validate() treats a schema's "format" keyword (e.g. "date",
# "uri") as advisory, not enforced, unless a FormatChecker is passed in
# explicitly — a deliberate design choice in the library, not an oversight
# here. Every schema test should go through validate() below rather than
# calling jsonschema.validate() directly, so format constraints are never
# silently skipped by a file that forgot to opt in.
FORMAT_CHECKER = jsonschema.FormatChecker()


def load_json(path: Path):
    return json.loads(path.read_text())


def validate(payload, schema):
    jsonschema.validate(instance=payload, schema=schema, format_checker=FORMAT_CHECKER)
