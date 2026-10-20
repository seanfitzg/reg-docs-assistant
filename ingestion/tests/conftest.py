# Puts ingestion/ on sys.path so test files can import the modules under test
# directly ("from ids import ...") rather than via a package path.
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
