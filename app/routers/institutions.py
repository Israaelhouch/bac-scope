"""/institutions and /streams: aggregated lists with pass rates."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from ..db import get_connection
from ..models import Institution, StreamSummary

router = APIRouter(tags=["aggregates"])

INST_SORT = {"pass_rate", "count", "avg_moyenne", "institution"}


@router.get("/institutions", response_model=list[Institution])
def list_institutions(
    stream: str | None = Query(None, description="Restrict to one stream"),
    min_count: int = Query(1, ge=1, description="Only schools with at least N students"),
    sort: str = Query("-pass_rate", description="Sort field; prefix '-' for descending"),
):
    """Each institution with its student count, pass rate, and average."""
    desc = sort.startswith("-")
    field = sort[1:] if desc else sort
    if field not in INST_SORT:
        raise HTTPException(400, f"Cannot sort by '{field}'. Allowed: {sorted(INST_SORT)}")

    where, params = "", []
    if stream:
        where = " WHERE stream = ?"
        params.append(stream)

    sql = f"""
        SELECT institution,
               COUNT(*)                                AS count,
               SUM(passed)                             AS passed,
               ROUND(1.0 * SUM(passed) / COUNT(*), 4)  AS pass_rate,
               ROUND(AVG(moyenne), 2)                  AS avg_moyenne
        FROM students{where}
        GROUP BY institution
        HAVING COUNT(*) >= ?
        ORDER BY {field} {'DESC' if desc else 'ASC'}
    """
    conn = get_connection(read_only=True)
    rows = conn.execute(sql, [*params, min_count]).fetchall()
    conn.close()
    return [Institution(**dict(r)) for r in rows if r["institution"]]


@router.get("/streams", response_model=list[StreamSummary])
def list_streams():
    """Each stream with student count, pass rate, and average."""
    conn = get_connection(read_only=True)
    rows = conn.execute(
        """SELECT stream,
                  COUNT(*)                                AS count,
                  SUM(passed)                             AS passed,
                  ROUND(1.0 * SUM(passed) / COUNT(*), 4)  AS pass_rate,
                  ROUND(AVG(moyenne), 2)                  AS avg_moyenne
           FROM students
           GROUP BY stream
           ORDER BY count DESC"""
    ).fetchall()
    conn.close()
    return [StreamSummary(**dict(r)) for r in rows]
