from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]  # rag/common/config.py -> repo root
DATA_DIR = ROOT / "data"
RAW_DIR = DATA_DIR / "raw"  # put source PDFs here (gitignored)
PROCESSED_DIR = DATA_DIR / "processed"  # extraction output (gitignored)
GOLDEN_DIR = DATA_DIR / "golden"  # evaluation questions (committed)
RUNS_DIR = ROOT / "runs"  # per-query traces and eval reports (gitignored)

# Extraction: fraction of page height treated as header / footer margin.
HEADER_FRACTION = 0.10
FOOTER_FRACTION = 0.10
# A margin line repeated on at least this share of pages is a running header/footer.
REPEAT_THRESHOLD = 0.2
