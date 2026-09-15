# pytest auto-loads any conftest.py it finds above the tests it's running,
# before running them — the standard place for shared setup like this.
#
# schema/tests/support.py can just say "from support import ..." because
# support.py lives in the *same* directory as the test files (pytest quietly
# adds a test file's own directory to sys.path when that directory has no
# __init__.py). Here the modules under test (ids.py, clean.py, pipeline.py,
# ...) live one directory up, in ingestion/ itself, not inside tests/ — so
# that trick alone wouldn't find them. This file fixes that by adding
# ingestion/ to sys.path explicitly, once, before any test file runs. After
# this, test files can import sibling modules the same simple way schema's
# tests do: "from ids import derive_document_id", not "from ingestion.ids
# import ...".
import sys
from pathlib import Path

# Path(__file__).parent is this file's directory (ingestion/tests/); .parent
# again walks up one more level to ingestion/ itself.
sys.path.insert(0, str(Path(__file__).parent.parent))
