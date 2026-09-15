# In Python, "#" starts a comment (the equivalent of "//" in C#).
# There's no project file or namespace declaration to worry about — a .py file
# just runs top to bottom. Indentation (whitespace) is significant here: it
# replaces C#'s { } braces for marking what's inside a function, loop, etc.

# "import" is like a C# "using" statement — it pulls a module into scope.
# json is part of Python's standard library, roughly equivalent to
# System.Text.Json — it converts between JSON text and Python objects.
import json

# pathlib is Python's modern object-oriented file-path API — think
# System.IO.Path / FileInfo, but paths are objects you can combine with "/"
# instead of calling Path.Combine(...).
from pathlib import Path

# jsonschema and pytest are third-party packages (like NuGet packages),
# declared in this project's dependency file and installed into a virtual
# environment (Python's equivalent of a per-project package folder).
# jsonschema validates JSON documents against a JSON Schema — comparable to
# NJsonSchema in .NET.
import jsonschema

# pytest is the test framework in play here — the rough equivalent of
# xUnit/nUnit. Unlike nUnit's [Test] attribute, pytest finds tests purely by
# naming convention: any function named test_* in a file named test_*.py is
# discovered and run automatically, no attribute/decorator required.
import pytest

# __file__ is a special variable Python fills in automatically with the path
# to the current source file (a bit like using reflection to get the
# executing assembly's location in .NET, but built into the language).
# .parent walks up one directory each time (like DirectoryInfo.Parent), and
# "/" here is Python's operator-overloaded path-join — equivalent to
# Path.Combine("fixtures", "trivial").
# This constant points at the folder holding the sample JSON files this test
# validates against.
TRIVIAL_FIXTURES = Path(__file__).parent.parent / "fixtures" / "trivial"


# "def" declares a function. There's no access modifier (public/private) and
# no declared return type — Python figures types out at runtime rather than
# at compile time. The body is just whatever's indented underneath.
def load(name):
    # (TRIVIAL_FIXTURES / name) builds the full file path, .read_text() reads
    # the whole file as a string (like File.ReadAllText), and json.loads(...)
    # parses that JSON string into a Python dict/list — analogous to
    # JsonSerializer.Deserialize<T>, except Python doesn't need a target type:
    # JSON objects become Python dicts, JSON arrays become Python lists, etc.
    return json.loads((TRIVIAL_FIXTURES / name).read_text())


# pytest treats this as a test case purely because its name starts with
# "test_" — no [Fact]/[Test] attribute needed. Think of it as the xUnit
# equivalent of:
#   [Fact] public void ValidFixturePassesValidation() { ... }
def test_valid_fixture_passes_validation():
    schema = load("schema.json")
    payload = load("valid.json")

    # jsonschema.validate() is the assertion here. It returns nothing on
    # success and *throws* on failure — so "no exception" is itself the pass
    # condition, similar to a call that would throw on invalid input in .NET
    # with no explicit Assert needed afterwards.
    jsonschema.validate(instance=payload, schema=schema)


def test_invalid_fixture_fails_validation():
    schema = load("schema.json")
    payload = load("invalid.json")

    # "with" opens a context manager — Python's equivalent of a C# "using"
    # block, guaranteeing setup/teardown around the indented code. Here,
    # pytest.raises(...) is a context manager that asserts an exception of
    # the given type is raised inside the block — the same idea as
    # Assert.Throws<ValidationError>(() => { ... }) in nUnit/xUnit.
    with pytest.raises(jsonschema.exceptions.ValidationError):
        jsonschema.validate(instance=payload, schema=schema)
