"""CSV ingestion: normalize Bac result files into students + grades.

Each CSV shares 7 core columns; the remaining columns are subject grades that
differ per stream. Core fields go into `students` (wide); subject grades go into
`grades` (long), so any subject in any stream fits with no schema change.
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from .db import get_connection, init_db

# Subject names differ across the 7 source files (with/without "ال", hamza vs
# bare alef, spacing). Canonicalize variants so the same subject isn't split.
SUBJECT_ALIASES = {
    "إعلامية": "الإعلامية",
    "الاعلامية": "الإعلامية",
    "إنقليزية": "الإنقليزية",
    "الانقليزية": "الإنقليزية",
    "عربية": "العربية",
    "فرنسية": "الفرنسية",
    "فلسفة": "الفلسفة",
    "رياضيات": "الرياضيات",
    "علوم فيزيائية": "العلوم الفيزيائية",
    "التاريخ و الجغرافيا": "التاريخ والجغرافيا",
}


def normalize_subject(name: str) -> str:
    """Collapse whitespace and map known spelling variants to one canonical name."""
    cleaned = " ".join(str(name).strip().split())
    return SUBJECT_ALIASES.get(cleaned, cleaned)


# The 7 columns shared across every stream file. Everything else is a subject.
CORE_COLUMNS = {
    "رقم التسجيل":   "registration_number",
    "رقم ب.ت.و":     "id_number",
    "الاسم":         "name",
    "المؤسسة":       "institution",
    "النتيجة":       "result_raw",
    "المجموع":       "total",
    "المعدل السنوي": "moyenne",
}


def parse_result(raw: str) -> tuple[int, str, str | None]:
    """Return (passed, status, mention) from the Arabic النتيجة text.

    - passed : 1 only if ناجح, else 0
    - status : ناجح / مؤجل / مرفوض (the outcome category)
    - mention: honor grade (حسن جدا / حسن / قريب من الحسن / متوسّط) for passed
               students only; None otherwise.

    Examples:
      'ناجح بملاحظة حسن جدا'   -> (1, 'ناجح', 'حسن جدا')
      'مؤجل إلى دورة المراقبة' -> (0, 'مؤجل', None)
      'مرفوض'                  -> (0, 'مرفوض', None)
    """
    s = (raw or "").strip()
    if s.startswith("ناجح"):
        mention = s.replace("ناجح بملاحظة", "").replace("ناجح", "").strip()
        return 1, "ناجح", (mention or None)
    if "مؤجل" in s:
        return 0, "مؤجل", None
    if "مرفوض" in s:
        return 0, "مرفوض", None
    return 0, "غير محدد", None


def _to_float(value) -> float | None:
    if value is None:
        return None
    if isinstance(value, float) and pd.isna(value):
        return None
    text = str(value).strip()
    if text == "" or text.lower() == "nan":
        return None
    try:
        return float(text)
    except ValueError:
        return None


# Minimum columns a file must contain to be a valid Bac results CSV.
REQUIRED_COLUMNS = ["رقم التسجيل", "الاسم", "النتيجة"]


def load_dataframe(
    df: pd.DataFrame, stream: str, filename: str, conn: sqlite3.Connection
) -> int:
    """Normalize a parsed CSV (DataFrame) for one stream into the DB.

    Used by both the seed script (from disk) and the upload endpoint (from
    memory). Raises ValueError if the required columns are missing.
    Returns the number of student rows inserted.
    """
    df.columns = [c.strip().lstrip("﻿") for c in df.columns]

    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(f"الملف ينقصه الأعمدة المطلوبة: {', '.join(missing)}")

    subject_cols = [c for c in df.columns if c not in CORE_COLUMNS]
    inserted = 0

    for _, row in df.iterrows():
        reg = _to_float(row.get("رقم التسجيل"))
        if reg is None:
            continue
        reg = int(reg)
        passed, status, mention = parse_result(row.get("النتيجة", ""))

        conn.execute(
            """INSERT OR REPLACE INTO students
               (registration_number, id_number, name, institution, stream,
                result_raw, passed, status, mention, total, moyenne)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (
                reg,
                (str(row.get("رقم ب.ت.و")).strip() if row.get("رقم ب.ت.و") else None),
                str(row.get("الاسم", "")).strip(),
                str(row.get("المؤسسة", "")).strip() or None,
                stream,
                str(row.get("النتيجة", "")).strip() or None,
                passed,
                status,
                mention,
                _to_float(row.get("المجموع")),
                _to_float(row.get("المعدل السنوي")),
            ),
        )

        # Remove any prior grades for this student (clean re-load), then insert.
        conn.execute("DELETE FROM grades WHERE registration_number = ?", (reg,))
        for subject in subject_cols:
            score = _to_float(row.get(subject))
            if score is not None:
                conn.execute(
                    "INSERT INTO grades (registration_number, subject, score) VALUES (?,?,?)",
                    (reg, normalize_subject(subject), score),
                )
        inserted += 1

    conn.execute(
        "INSERT INTO datasets (stream, filename, row_count, uploaded_at) VALUES (?,?,?,?)",
        (stream, filename, inserted, datetime.now(timezone.utc).isoformat()),
    )
    conn.commit()
    return inserted


def load_csv(path: str | Path, stream: str, conn: sqlite3.Connection) -> int:
    """Load one CSV file from disk for a given stream. Returns rows inserted."""
    path = Path(path)
    df = pd.read_csv(path, dtype=str, encoding="utf-8-sig")
    return load_dataframe(df, stream, path.name, conn)


def init_and_get_conn() -> sqlite3.Connection:
    conn = get_connection()
    init_db(conn)
    return conn
