from pathlib import Path

from regdocs_ingestion.pipeline import run_pipeline

repo_root = Path(__file__).parents[3]
results = run_pipeline(
    manifest_path=repo_root / "ingestion" / "manifest.json",
    corpus_dir=repo_root / "corpus",
    output_dir=repo_root / "ingestion" / "output",
)
print(f"Ingested {len(results)} documents into ingestion/output")
