# Tests for document.schema.json and chunk.schema.json (issue #3), plus two
# relational checks that individual per-file validation can't express on its
# own: that a "supersedes" fixture genuinely points at another fixture's id,
# and that a Document's active_chunking_generation_id genuinely picks out one
# generation among more than one Chunk generation on disk.
#
# See test_harness.py for the basics (imports, pathlib, jsonschema.validate,
# pytest.raises) — this file only comments on what's new here. load_json()
# and validate() (which enforces "format" constraints, unlike calling
# jsonschema.validate() directly) live in support.py so they aren't
# redefined per file.

from pathlib import Path

import jsonschema
import pytest

from support import load_json, validate

SCHEMA_DIR = Path(__file__).parent.parent
DOCUMENT_SCHEMA = SCHEMA_DIR / "document.schema.json"
CHUNK_SCHEMA = SCHEMA_DIR / "chunk.schema.json"
DOCUMENT_FIXTURES = SCHEMA_DIR / "fixtures" / "document"
CHUNK_FIXTURES = SCHEMA_DIR / "fixtures" / "chunk"


# ---- Document schema ----

def test_original_document_passes_validation():
    schema = load_json(DOCUMENT_SCHEMA)
    payload = load_json(DOCUMENT_FIXTURES / "valid-original.json")

    validate(payload, schema)


def test_superseding_document_passes_validation():
    schema = load_json(DOCUMENT_SCHEMA)
    payload = load_json(DOCUMENT_FIXTURES / "valid-superseding.json")

    validate(payload, schema)


def test_superseding_document_references_the_original_by_id():
    original = load_json(DOCUMENT_FIXTURES / "valid-original.json")
    superseding = load_json(DOCUMENT_FIXTURES / "valid-superseding.json")

    # Square brackets on a dict do a key lookup — like a C# Dictionary's
    # indexer, except there's no declared value type since Python resolves
    # types at runtime. A missing key raises KeyError rather than returning
    # null, so this line also doubles as "the field is actually present".
    #
    # "assert" is a language keyword here, not a method call — pytest
    # rewrites it under the hood so that on failure it reports the actual
    # values of both sides (e.g. "assert 'doc-1' == 'doc-2'"), similar to
    # what Assert.AreEqual(expected, actual) gives you in nUnit, but without
    # having to call a separate Assert API.
    assert superseding["supersedes"] == original["id"]


def test_invalid_document_fails_validation():
    schema = load_json(DOCUMENT_SCHEMA)
    payload = load_json(DOCUMENT_FIXTURES / "invalid-missing-required.json")

    with pytest.raises(jsonschema.exceptions.ValidationError):
        validate(payload, schema)


def test_document_with_malformed_date_fails_validation():
    # Proves support.validate()'s format enforcement is actually doing
    # something for "date": without it, "not-a-date" would pass.
    schema = load_json(DOCUMENT_SCHEMA)
    payload = load_json(DOCUMENT_FIXTURES / "invalid-bad-date-format.json")

    with pytest.raises(jsonschema.exceptions.ValidationError):
        validate(payload, schema)


def test_document_with_malformed_url_fails_validation():
    # Same proof, for "uri" specifically — jsonschema's default install
    # doesn't even register a "uri" checker (only "date" works out of the
    # box), which is why requirements.txt pins jsonschema[format].
    schema = load_json(DOCUMENT_SCHEMA)
    payload = load_json(DOCUMENT_FIXTURES / "invalid-bad-uri-format.json")

    with pytest.raises(jsonschema.exceptions.ValidationError):
        validate(payload, schema)


def test_document_with_empty_id_fails_validation():
    schema = load_json(DOCUMENT_SCHEMA)
    payload = load_json(DOCUMENT_FIXTURES / "invalid-empty-id.json")

    with pytest.raises(jsonschema.exceptions.ValidationError):
        validate(payload, schema)


# ---- Chunk schema ----

def test_generation_one_chunk_passes_validation():
    schema = load_json(CHUNK_SCHEMA)
    payload = load_json(CHUNK_FIXTURES / "valid-generation-1.json")

    validate(payload, schema)


def test_generation_two_chunk_passes_validation():
    schema = load_json(CHUNK_SCHEMA)
    payload = load_json(CHUNK_FIXTURES / "valid-generation-2.json")

    validate(payload, schema)


def test_invalid_chunk_fails_validation():
    schema = load_json(CHUNK_SCHEMA)
    payload = load_json(CHUNK_FIXTURES / "invalid-missing-required.json")

    with pytest.raises(jsonschema.exceptions.ValidationError):
        validate(payload, schema)


def test_chunk_with_empty_text_fails_validation():
    schema = load_json(CHUNK_SCHEMA)
    payload = load_json(CHUNK_FIXTURES / "invalid-empty-text.json")

    with pytest.raises(jsonschema.exceptions.ValidationError):
        validate(payload, schema)


# ---- Cross-fixture relationship: active generation among more than one ----

def test_document_active_generation_points_at_the_correct_chunk_generation():
    document = load_json(DOCUMENT_FIXTURES / "valid-original.json")
    generation_one = load_json(CHUNK_FIXTURES / "valid-generation-1.json")
    generation_two = load_json(CHUNK_FIXTURES / "valid-generation-2.json")

    # Both Chunks belong to the same Document, but to two different
    # generations — proving more than one generation genuinely exists here.
    assert generation_one["document_id"] == document["id"]
    assert generation_two["document_id"] == document["id"]
    assert generation_one["chunking_generation_id"] != generation_two["chunking_generation_id"]

    # The Document's active pointer matches generation_two specifically —
    # combined with the inequality above, that already establishes
    # generation_one is not the active one too, so a third assertion here
    # would just restate what these two already guarantee.
    assert document["active_chunking_generation_id"] == generation_two["chunking_generation_id"]
