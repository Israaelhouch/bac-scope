"""/students endpoints: filtered list + single student with grades."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from ..db import get_connection
from ..models import Grade, Student, StudentDetail, StudentList

router = APIRouter(tags=["students"])

# Columns the client is allowed to sort by (prevents SQL injection via sort).
SORT_FIELDS = {"moyenne", "total", "name", "stream", "institution"}


def _build_filters(
    stream, institution, mention, passed, min_avg, max_avg, search
) -> tuple[str, list]:
    """Return a SQL WHERE fragment + parameters from the given filters."""
    clauses, params = [], []
    if stream:
        clauses.append("stream = ?"); params.append(stream)
    if institution:
        clauses.append("institution = ?"); params.append(institution)
    if mention:
        clauses.append("mention = ?"); params.append(mention)
    if passed is not None:
        clauses.append("passed = ?"); params.append(1 if passed else 0)
    if min_avg is not None:
        clauses.append("moyenne >= ?"); params.append(min_avg)
    if max_avg is not None:
        clauses.append("moyenne <= ?"); params.append(max_avg)
    if search:
        clauses.append("name LIKE ?"); params.append(f"%{search}%")
    where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
    return where, params


@router.get("/students", response_model=StudentList)
def list_students(
    stream: str | None = Query(None, description="Filter by stream (شعبة)"),
    institution: str | None = Query(None, description="Filter by institution"),
    mention: str | None = Query(None, description="Filter by mention (ملاحظة)"),
    passed: bool | None = Query(None, description="Only passed / only failed"),
    min_avg: float | None = Query(None, description="Minimum annual average"),
    max_avg: float | None = Query(None, description="Maximum annual average"),
    search: str | None = Query(None, description="Search in student name"),
    sort: str = Query("-moyenne", description="Sort field; prefix '-' for descending"),
    limit: int = Query(50, ge=1, le=1000),
    offset: int = Query(0, ge=0),
):
    """List students matching the filters, sorted and paginated."""
    where, params = _build_filters(
        stream, institution, mention, passed, min_avg, max_avg, search
    )

    # Parse sort: leading '-' means descending.
    desc = sort.startswith("-")
    field = sort[1:] if desc else sort
    if field not in SORT_FIELDS:
        raise HTTPException(400, f"Cannot sort by '{field}'. Allowed: {sorted(SORT_FIELDS)}")
    order = f" ORDER BY {field} {'DESC' if desc else 'ASC'}"

    conn = get_connection(read_only=True)
    total = conn.execute(f"SELECT COUNT(*) FROM students{where}", params).fetchone()[0]
    rows = conn.execute(
        f"SELECT * FROM students{where}{order} LIMIT ? OFFSET ?",
        [*params, limit, offset],
    ).fetchall()
    conn.close()

    items = [Student(**dict(r)) for r in rows]
    return StudentList(
        count=len(items), total=total, limit=limit, offset=offset, items=items
    )


@router.get("/students/{registration_number}", response_model=StudentDetail)
def get_student(registration_number: int):
    """Return one student's full record plus all their subject grades."""
    conn = get_connection(read_only=True)
    row = conn.execute(
        "SELECT * FROM students WHERE registration_number = ?",
        (registration_number,),
    ).fetchone()
    if row is None:
        conn.close()
        raise HTTPException(404, "Student not found")
    grades = conn.execute(
        "SELECT subject, score FROM grades WHERE registration_number = ? ORDER BY score DESC",
        (registration_number,),
    ).fetchall()
    conn.close()
    return StudentDetail(**dict(row), grades=[Grade(**dict(g)) for g in grades])
