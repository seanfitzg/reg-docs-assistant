# Puts track-b/ on sys.path so tests can "from retriever import ...".
#
# store/, store/tests/ and eval/ are added too: the retriever reuses /store's
# db.py and embed.py, the integration tests reuse store/tests' Postgres
# fixtures (DB_URL, requires_postgres, clean_db), and the opt-in parity test
# reuses eval/'s match rule and baseline run report.
import sys
from pathlib import Path

TRACK_B_DIR = Path(__file__).parent.parent
REPO_DIR = TRACK_B_DIR.parent

sys.path.insert(0, str(TRACK_B_DIR))
sys.path.insert(0, str(REPO_DIR / "store"))
sys.path.insert(0, str(REPO_DIR / "store" / "tests"))
sys.path.insert(0, str(REPO_DIR / "eval"))
