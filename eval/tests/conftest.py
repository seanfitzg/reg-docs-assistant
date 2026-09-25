# Same trick as store/tests/conftest.py: the modules under test live one
# directory up from tests/, so this adds eval/ to sys.path once, before any
# test file runs, letting test files write "from corpus import ..." instead
# of a package-relative import.
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
