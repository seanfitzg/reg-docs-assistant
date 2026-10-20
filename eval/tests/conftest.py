# Puts eval/ on sys.path so test files can "from corpus import ...".
#
# store/ and store/tests/ are added too: run_eval.py reuses /store's db.py and
# embed.py (issue #32), and test_run_eval.py reuses store/tests' Postgres
# fixtures (DB_URL, requires_postgres, clean_db).
import sys
from pathlib import Path

EVAL_DIR = Path(__file__).parent.parent
STORE_DIR = EVAL_DIR.parent / "store"

sys.path.insert(0, str(EVAL_DIR))
sys.path.insert(0, str(STORE_DIR))
sys.path.insert(0, str(STORE_DIR / "tests"))
