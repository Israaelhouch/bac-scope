"""/ask: natural-language question -> SQL -> validated result + auto-viz."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from .. import autoviz, llm, nl2sql
from ..db import get_connection

router = APIRouter(tags=["ask"])


class Scope(BaseModel):
    """Optional filters to constrain the question to a subset of the data."""
    stream: str | None = None
    institution: str | None = None
    passed: bool | None = None
    min_bac: float | None = None       # total — معدل الباك
    max_bac: float | None = None
    min_annual: float | None = None    # moyenne — المعدل السنوي
    max_annual: float | None = None


class AskRequest(BaseModel):
    question: str = Field(..., min_length=2, description="Question in Arabic/French/English")
    scope: Scope | None = Field(None, description="Optional filters to scope the answer")


@router.get("/ask/status")
def ask_status():
    """Whether the natural-language endpoint is enabled (Groq key present)."""
    return {"enabled": llm.is_configured()}


@router.post("/ask")
def ask(payload: AskRequest):
    """Answer a free-form question by generating and running safe SQL.

    Returns the generated SQL (for transparency), the rows, and an auto-picked
    chart spec. The LLM only writes SQL; we validate it and run it read-only.
    """
    conn = get_connection(read_only=True)
    scope_dict = payload.scope.model_dump(exclude_none=True) if payload.scope else {}
    prompt = nl2sql.build_system_prompt(conn, scope=scope_dict)

    # 1) LLM writes SQL.
    try:
        raw_sql = llm.generate_sql(payload.question, prompt)
    except llm.LLMError as exc:
        conn.close()
        raise HTTPException(503, str(exc))

    # 2) Validate (SELECT-only, single statement, enforced LIMIT).
    try:
        sql = nl2sql.validate_sql(raw_sql)
    except ValueError as exc:
        conn.close()
        raise HTTPException(422, {"error": str(exc), "generated_sql": raw_sql})

    # 3) Execute read-only.
    try:
        columns, rows = nl2sql.run_query(sql, conn)
    except Exception as exc:  # noqa: BLE001
        conn.close()
        raise HTTPException(422, {"error": f"فشل تنفيذ الاستعلام: {exc}", "sql": sql})
    finally:
        conn.close()

    # 4) Auto-visualize by result shape.
    viz = autoviz.build(columns, rows)

    return {
        "question": payload.question,
        "scope": scope_dict or None,   # echo applied scope for transparency
        "sql": sql,
        "columns": columns,
        "row_count": len(rows),
        "data": rows,
        **viz,  # kind, chart, and (for stat) label/value
    }
