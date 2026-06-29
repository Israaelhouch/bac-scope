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

    files = sorted(source.glob("*.csv"))
    if not files:
        print(f"  ! no CSV files found in {source}")
        conn.close()
        return

    total, loaded = 0, 0
    for path in files:
        # Known files use their mapped stream; any other file uses its filename
        # as the stream (export-format files ignore this and read `section`).
        stream = FILE_TO_STREAM.get(path.name, path.stem)
        try:
            n = load_csv(path, stream, conn)
        except Exception as exc:  # noqa: BLE001 — keep going if one file is bad
            print(f"  ! {path.name}: {exc}")
            continue
        total += n
        loaded += 1
        print(f"  + {stream:<14} {n:>4} students  ({path.name})")
    conn.close()
    print(f"\nSeed complete: {total} students from {loaded}/{len(files)} file(s).")


if __name__ == "__main__":
    main()
