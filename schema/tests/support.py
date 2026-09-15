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
    # "path: Path" is a type hint — documentation for readers/tooling, not
    # enforced at runtime the way a C# parameter type is. Nothing stops you
    # passing a plain string here; it would just fail at .read_text() instead.
    # .read_text() reads the whole file as a string (like File.ReadAllText);
    # json.loads(...) parses that JSON string into a Python dict/list —
    # comparable to JsonSerializer.Deserialize<T>, but with no target type
    # since JSON objects become dicts and JSON arrays become lists directly.
    return json.loads(path.read_text())


def validate(payload, schema):
    # instance=..., schema=..., format_checker=... are keyword arguments —
    # like C# named parameters (Foo(instance: payload)) — naming which
    # parameter each value binds to rather than relying on position.
    jsonschema.validate(instance=payload, schema=schema, format_checker=FORMAT_CHECKER)
