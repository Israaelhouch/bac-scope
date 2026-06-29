"""/datasets: upload new CSVs (auto-merge) and list what's been loaded."""
from __future__ import annotations

import io
from pathlib import Path

import pandas as pd
from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from ..db import get_connection
from ..ingest import load_dataframe

router = APIRouter(tags=["datasets"])


@router.get("/datasets")
def list_datasets():
    """The files loaded so far, with their stream and row counts."""
    conn = get_connection(read_only=True)
    rows = [dict(r) for r in conn.execute(
        "SELECT id, stream, filename, row_count, uploaded_at "
        "FROM datasets ORDER BY uploaded_at DESC"
    ).fetchall()]
    conn.close()
    return {"count": len(rows), "items": rows}


@router.post("/datasets")
async def upload_dataset(
    file: UploadFile = File(..., description="A Bac results CSV"),
    stream: str | None = Form(None, description="Stream name; defaults to the file name"),
):
    """Upload a CSV; it's normalized and merged into the database.

    Students with a registration number already present are updated (re-upload
    safe). The stream defaults to the file name if not provided.
    """
    if not file.filename.lower().endswith(".csv"):
        raise HTTPException(400, "الملف يجب أن يكون من نوع CSV")

    raw = await file.read()
    try:
        df = pd.read_csv(io.BytesIO(raw), dtype=str, encoding="utf-8-sig")
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(400, f"تعذّر قراءة الملف: {exc}")

    stream_name = (stream or Path(file.filename).stem).strip()
    if not stream_name:
        raise HTTPException(400, "اسم الشعبة مطلوب")

    conn = get_connection()  # writable
    try:
        inserted = load_dataframe(df, stream_name, file.filename, conn)
    except ValueError as exc:
        conn.close()
        raise HTTPException(422, str(exc))
    conn.close()

    return {
        "status": "ok",
        "stream": stream_name,
        "filename": file.filename,
        "rows_inserted": inserted,
    }
