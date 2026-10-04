from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
RAW_DIR = DATA_DIR / "raw"  # put source PDFs here (gitignored)
PROCESSED_DIR = DATA_DIR / "processed"  # extraction output (gitignored)
GOLDEN_DIR = DATA_DIR / "golden"  # evaluation questions (committed)
RUNS_DIR = ROOT / "runs"  # per-query traces and eval reports (gitignored)

# Extraction: fraction of page height treated as header / footer margin.
HEADER_FRACTION = 0.07
FOOTER_FRACTION = 0.07
# A margin line repeated on at least this share of pages is a running header/footer.
REPEAT_THRESHOLD = 0.2
