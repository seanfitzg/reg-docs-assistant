# Same trick as ingestion/tests/conftest.py: loader.py lives one directory
# up from tests/, so this adds store/ to sys.path once, before any test
# file runs, letting test files write "from loader import load_store"
# instead of a package-relative import.
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
