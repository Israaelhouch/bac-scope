"""Seed the SQLite database from CSV files.

Uses data/raw/ if it contains CSVs (your real data, gitignored); otherwise
falls back to data/sample/ (committed anonymized sample) so a fresh clone works.

Run from the project root:  python -m scripts.seed
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db import reset_db, get_connection  # noqa: E402
from app.ingest import load_csv  # noqa: E402

_BASE = Path(__file__).resolve().parent.parent / "data"
RAW_DIR = _BASE / "raw"
SAMPLE_DIR = _BASE / "sample"


def _source_dir() -> Path:
    """Prefer real data in data/raw/, else the committed sample."""
    if RAW_DIR.exists() and any(RAW_DIR.glob("*.csv")):
        return RAW_DIR
    return SAMPLE_DIR

# Map each raw file to its Bac stream (شعبة).
FILE_TO_STREAM = {
    "math.csv":         "رياضيات",
    "sciences_exp.csv": "علوم تجريبية",
    "technique.csv":    "علوم تقنية",
    "informatique.csv": "علوم الإعلامية",
    "economie.csv":     "اقتصاد وتصرف",
    "lettres.csv":      "آداب",
    "sport.csv":        "رياضة",
}


def main() -> None:
    source = _source_dir()
    print(f"Seeding from: {source.relative_to(_BASE.parent)}")
    reset_db()
    conn = get_connection()
    total = 0
    for filename, stream in FILE_TO_STREAM.items():
        path = source / filename
        if not path.exists():
            print(f"  ! missing {filename}, skipping")
            continue
        n = load_csv(path, stream, conn)
        total += n
        print(f"  + {stream:<14} {n:>4} students  ({filename})")
    conn.close()
    print(f"\nSeed complete: {total} students across {len(FILE_TO_STREAM)} streams.")


if __name__ == "__main__":
    main()
