"""CSV ingestion: normalize Bac result files into students + grades.

Each CSV shares 7 core columns; the remaining columns are subject grades that
differ per stream. Core fields go into `students` (wide); subject grades go into
`grades` (long), so any subject in any stream fits with no schema change.
"""
from __future__ import annotations

import csv
import io
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from .db import get_connection, init_db

# Tatweel (ـ) + Arabic diacritics/harakat + superscript alef. Does NOT touch
# hamza letters (أ إ آ ؤ ئ ء), which are real letters.
_AR_MARKS = re.compile(r"[ـً-ٰٟ]")


def _clean_ar(text) -> str:
    """Strip tatweel + diacritics and collapse whitespace (e.g. الـرِّيـاضـيـات -> الرياضيات)."""
    if text is None:
        return ""
    return re.sub(r"\s+", " ", _AR_MARKS.sub("", str(text))).strip()


# Subject names differ across files (with/without "ال", hamza vs bare alef,
# spacing, tatweel/diacritics). Canonicalize so the same subject isn't split.
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

# Stream (section) name variants -> canonical names used across the app.
STREAM_ALIASES = {
    "إقتصاد و تصرف": "اقتصاد وتصرف",
    "اقتصاد و تصرف": "اقتصاد وتصرف",
    "الآداب": "آداب",
    "الرياضيات": "رياضيات",
    "العلوم تجريبية": "علوم تجريبية",
    "علوم الاعلامية": "علوم الإعلامية",
}


def normalize_subject(name: str) -> str:
    """Clean (tatweel/diacritics/whitespace) and map variants to one canonical name."""
    cleaned = _clean_ar(name)
    return SUBJECT_ALIASES.get(cleaned, cleaned)


def normalize_stream(name: str) -> str:
    """Clean and map a section/stream name to its canonical form."""
    cleaned = _clean_ar(name)
    return STREAM_ALIASES.get(cleaned, cleaned)


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
    s = _clean_ar(raw)
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


# --- export format (English headers + grade_N/subject_N pairs) ---------------

EXPORT_REQUIRED = ["registration_number", "student_name", "result_status"]


def load_export(
    header: list[str], rows: list[list[str]], filename: str, conn: sqlite3.Connection
) -> int:
    """Parse the English export format with a variable number of grade/subject pairs.

    The stream comes from each row's `section`; subject pairs are everything after
    `annual_average`, read flexibly so rows with extra subjects aren't dropped.
    """
    header = [c.strip().lstrip("﻿") for c in header]
    idx = {name: i for i, name in enumerate(header)}
    missing = [c for c in EXPORT_REQUIRED if c not in idx]
    if missing:
        raise ValueError(f"الملف ينقصه الأعمدة المطلوبة: {', '.join(missing)}")

    pairs_start = idx.get("annual_average", idx["result_status"]) + 1

    def cell(row, name):
        i = idx.get(name)
        return row[i] if i is not None and i < len(row) else None

    inserted = 0
    for row in rows:
        if not row or len(row) <= idx["registration_number"]:
            continue
        reg = _to_float(cell(row, "registration_number"))
        if reg is None:
            continue
        name = str(cell(row, "student_name") or "").strip()
        if not name:
            continue  # incomplete record: reg + status only, no name/section/grades
        reg = int(reg)
        passed, status, mention = parse_result(cell(row, "result_status") or "")

        conn.execute(
            """INSERT OR REPLACE INTO students
               (registration_number, id_number, name, institution, stream,
                result_raw, passed, status, mention, total, moyenne)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (
                reg,
                (str(cell(row, "cin_number")).strip() or None) if cell(row, "cin_number") else None,
                name,
                _clean_ar(cell(row, "institution")) or None,
                normalize_stream(cell(row, "section") or ""),
                _clean_ar(cell(row, "result_status")) or None,
                passed,
                status,
                mention,
                _to_float(cell(row, "overall_grade")),
                _to_float(cell(row, "annual_average")),
            ),
        )
        conn.execute("DELETE FROM grades WHERE registration_number = ?", (reg,))
        pairs = row[pairs_start:]
        for i in range(0, len(pairs) - 1, 2):
            score = _to_float(pairs[i])
            subject = pairs[i + 1]
            if subject and str(subject).strip() and score is not None:
                conn.execute(
                    "INSERT INTO grades (registration_number, subject, score) VALUES (?,?,?)",
                    (reg, normalize_subject(subject), score),
                )
        inserted += 1

    conn.execute(
        "INSERT INTO datasets (stream, filename, row_count, uploaded_at) VALUES (?,?,?,?)",
        ("متعدد (export)", filename, inserted, datetime.now(timezone.utc).isoformat()),
    )
    conn.commit()
    return inserted


# --- dispatcher --------------------------------------------------------------

def detect_format(header: list[str]) -> str:
    h = [c.strip().lstrip("﻿") for c in header]
    if "رقم التسجيل" in h:
        return "arabic"
    if "registration_number" in h or "student_name" in h:
        return "export"
    return "unknown"


def load_text(
    text: str, stream: str | None, filename: str, conn: sqlite3.Connection
) -> int:
    """Detect the format from the header and route to the right parser."""
    all_rows = list(csv.reader(io.StringIO(text)))
    if not all_rows:
        raise ValueError("الملف فارغ")
    fmt = detect_format(all_rows[0])
    if fmt == "arabic":
        df = pd.read_csv(io.StringIO(text), dtype=str, encoding="utf-8-sig")
        return load_dataframe(df, stream or Path(filename).stem, filename, conn)
    if fmt == "export":
        return load_export(all_rows[0], all_rows[1:], filename, conn)
    raise ValueError(
        "صيغة الملف غير معروفة. يجب أن يحتوي على أعمدة عربية "
        "(رقم التسجيل، الاسم، النتيجة) أو أعمدة التصدير (registration_number ...)."
    )


def load_csv(path: str | Path, stream: str, conn: sqlite3.Connection) -> int:
    """Load one CSV file from disk (any supported format). Returns rows inserted."""
    path = Path(path)
    text = path.read_text(encoding="utf-8-sig")
    return load_text(text, stream, path.name, conn)


def init_and_get_conn() -> sqlite3.Connection:
    conn = get_connection()
    init_db(conn)
    return conn
