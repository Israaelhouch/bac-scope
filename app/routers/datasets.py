"""/datasets: upload new CSVs (auto-merge) and list what's been loaded."""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from ..db import get_connection
from ..ingest import load_text

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
    text = raw.decode("utf-8-sig", errors="replace")

    conn = get_connection()  # writable
    try:
        # Arabic format uses the given/derived stream; export format reads its own.
        inserted = load_text(text, stream or Path(file.filename).stem, file.filename, conn)
    except ValueError as exc:
        conn.close()
        raise HTTPException(422, str(exc))
    conn.close()

    return {
        "status": "ok",
        "filename": file.filename,
        "rows_inserted": inserted,
    }
