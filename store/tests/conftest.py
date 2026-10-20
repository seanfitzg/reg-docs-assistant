# Puts store/ on sys.path so test files can "from loader import load_store".
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
