# Checks the real eval/dataset.json (issue #29): valid against its JSON
# Schema, and free of the relational problems check_dataset.find_problems
# looks for. This is the safety net while hand-writing Eval Cases (#31) --
# run it after every edit.

import json
from pathlib import Path

import jsonschema
import pytest

from regdocs_eval.check_dataset import find_problems
from regdocs_eval.corpus import DEFAULT_OUTPUT_DIR, load_active_chunks

EVAL_DIR = Path(__file__).parent.parent
DATASET = EVAL_DIR / "dataset.json"
SCHEMA = EVAL_DIR.parent / "schema" / "eval-dataset.schema.json"

# ingestion/output/ is gitignored (a regenerable projection, ADR-0012), so a
# fresh clone won't have it: skip rather than fail.
requires_ingestion_output = pytest.mark.skipif(
    not (DEFAULT_OUTPUT_DIR / "chunks").is_dir(),
    reason="ingestion/output not present -- run the ingestion pipeline first",
)


def _load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.mark.parametrize(
    "dataset_path",
    [
        DATASET,
        # Keeps the unit-test fixture honest: if the schema tightens,
        # test_check_dataset.py shouldn't keep testing a dataset shape the
        # real file could no longer have.
        Path(__file__).parent / "fixtures" / "valid-dataset.json",
    ],
    ids=["eval/dataset.json", "fixtures/valid-dataset.json"],
)
def test_dataset_matches_schema(dataset_path):
    # FormatChecker enforced explicitly, as in regdocs_schema.testing.
    jsonschema.validate(
        instance=_load(dataset_path),
        schema=_load(SCHEMA),
        format_checker=jsonschema.FormatChecker(),
    )


@requires_ingestion_output
def test_dataset_has_no_duplicate_ids_or_missing_locators():
    problems = find_problems(_load(DATASET), load_active_chunks())

    # The joined message makes a failure print every problem at once.
    assert problems == [], "\n".join(problems)
