"""Re-run the whole ingestion chain: PDFs -> JSON -> Postgres -> embeddings.

Needs Postgres up (docker compose up -d in store/) and Ollama running.
"""

import subprocess
import sys
from pathlib import Path

repo_root = Path(__file__).parents[1]
steps = [
    "regdocs_ingestion",
    "regdocs_store.loader",
    "regdocs_store.embed",
]

for module in steps:
    print(f"\n==> python -m {module}", flush=True)
    result = subprocess.run([sys.executable, "-m", module], check=False, cwd=repo_root)
    if result.returncode != 0:
        sys.exit(result.returncode)
