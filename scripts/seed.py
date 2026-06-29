"""Seed the SQLite database from the 7 raw CSV files in data/raw/.

Run from the project root:  python -m scripts.seed
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db import reset_db, get_connection  # noqa: E402
from app.ingest import load_csv  # noqa: E402

RAW_DIR = Path(__file__).resolve().parent.parent / "data" / "raw"

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
    reset_db()
    conn = get_connection()
    total = 0
    for filename, stream in FILE_TO_STREAM.items():
        path = RAW_DIR / filename
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
