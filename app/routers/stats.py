"""/stats endpoints: aggregates + a ready-to-render Plotly chart spec.

Every endpoint returns the same shape:
    { "data": [ ...rows... ], "chart": { Plotly spec } }
so a front end can render `chart` directly OR build its own visual from `data`.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from .. import charts
from ..db import get_connection

router = APIRouter(prefix="/stats", tags=["stats"])


@router.get("/pass-rates")
def pass_rates(
    group_by: str = Query("stream", description="'stream' or 'institution'"),
    min_count: int = Query(1, ge=1, description="Min students per group (institution)"),
):
    """Pass rate per stream or per institution."""
    if group_by not in {"stream", "institution"}:
        raise HTTPException(400, "group_by must be 'stream' or 'institution'")

    conn = get_connection(read_only=True)
    rows = [dict(r) for r in conn.execute(
        f"""SELECT {group_by} AS group_name,
                   COUNT(*)                                AS count,
                   SUM(passed)                             AS passed,
                   ROUND(100.0 * SUM(passed) / COUNT(*), 1) AS pass_rate
            FROM students
            WHERE {group_by} IS NOT NULL
            GROUP BY {group_by}
            HAVING COUNT(*) >= ?
            ORDER BY pass_rate DESC""",
        (min_count,),
    ).fetchall()]
    conn.close()

    chart = charts.bar(
        [r["group_name"] for r in rows],
        [r["pass_rate"] for r in rows],
        title=f"نسبة النجاح حسب {'الشعبة' if group_by == 'stream' else 'المؤسسة'}",
        y_title="نسبة النجاح %",
    )
    return {"data": rows, "chart": chart}


@router.get("/mentions")
def mentions(stream: str | None = Query(None, description="Restrict to one stream")):
    """Distribution of honor grades (ملاحظات) among passed students."""
    clauses = ["mention IS NOT NULL"]
    params: list = []
    if stream:
        clauses.append("stream = ?"); params.append(stream)
    where = " WHERE " + " AND ".join(clauses)

    conn = get_connection(read_only=True)
    rows = [dict(r) for r in conn.execute(
        f"""SELECT mention, COUNT(*) AS count
            FROM students{where}
            GROUP BY mention ORDER BY count DESC""",
        params,
    ).fetchall()]
    conn.close()

    chart = charts.pie(
        [r["mention"] for r in rows],
        [r["count"] for r in rows],
        title="توزيع الملاحظات" + (f" — {stream}" if stream else ""),
    )
    return {"data": rows, "chart": chart}


@router.get("/status")
def status_breakdown(stream: str | None = Query(None, description="Restrict to one stream")):
    """Outcome breakdown: ناجح / مؤجل / مرفوض."""
    where, params = ("", [])
    if stream:
        where, params = (" WHERE stream = ?", [stream])

    conn = get_connection(read_only=True)
    rows = [dict(r) for r in conn.execute(
        f"""SELECT status, COUNT(*) AS count
            FROM students{where}
            GROUP BY status ORDER BY count DESC""",
        params,
    ).fetchall()]
    conn.close()

    chart = charts.pie(
        [r["status"] for r in rows],
        [r["count"] for r in rows],
        title="توزيع النتائج" + (f" — {stream}" if stream else ""),
    )
    return {"data": rows, "chart": chart}


@router.get("/subject-averages")
def subject_averages(
    stream: str | None = Query(None, description="Restrict to one stream"),
    min_count: int = Query(5, ge=1, description="Ignore subjects with few grades"),
):
    """Average grade per subject (optionally within one stream)."""
    where, params = ("", [])
    if stream:
        where, params = (" WHERE s.stream = ?", [stream])

    conn = get_connection(read_only=True)
    rows = [dict(r) for r in conn.execute(
        f"""SELECT g.subject,
                   ROUND(AVG(g.score), 2) AS avg_score,
                   COUNT(*)               AS count
            FROM grades g JOIN students s
              ON g.registration_number = s.registration_number
            {where}
            GROUP BY g.subject
            HAVING COUNT(*) >= ?
            ORDER BY avg_score DESC""",
        [*params, min_count],
    ).fetchall()]
    conn.close()

    chart = charts.bar(
        [r["subject"] for r in rows],
        [r["avg_score"] for r in rows],
        title="معدل كل مادة" + (f" — {stream}" if stream else ""),
        y_title="المعدل /20",
    )
    return {"data": rows, "chart": chart}


@router.get("/top-performers")
def top_performers(
    limit: int = Query(10, ge=1, le=100),
    stream: str | None = Query(None),
    institution: str | None = Query(None),
    subject: str | None = Query(None, description="Rank by this subject's grade"),
    per_stream: bool = Query(False, description="Top N within EACH stream"),
    by: str = Query("total", description="Rank by 'total' or 'moyenne' (ignored if subject set)"),
):
    """Highest achievers — overall, per stream, or by a specific subject."""
    conn = get_connection(read_only=True)

    if subject:
        # Rank by a single subject's score.
        where = ["g.subject = ?"]
        params: list = [subject]
        if stream:
            where.append("s.stream = ?"); params.append(stream)
        if institution:
            where.append("s.institution = ?"); params.append(institution)
        rows = [dict(r) for r in conn.execute(
            f"""SELECT s.name, s.stream, s.institution, g.score AS value
                FROM grades g JOIN students s
                  ON g.registration_number = s.registration_number
                WHERE {' AND '.join(where)}
                ORDER BY g.score DESC LIMIT ?""",
            [*params, limit],
        ).fetchall()]
        title = f"الأوائل في مادة {subject}"
    else:
        if by not in {"total", "moyenne"}:
            raise HTTPException(400, "by must be 'total' or 'moyenne'")
        where, params = [], []
        if stream:
            where.append("stream = ?"); params.append(stream)
        if institution:
            where.append("institution = ?"); params.append(institution)
        wsql = (" WHERE " + " AND ".join(where)) if where else ""

        if per_stream:
            rows = [dict(r) for r in conn.execute(
                f"""SELECT name, stream, institution, {by} AS value FROM (
                        SELECT *, ROW_NUMBER() OVER
                            (PARTITION BY stream ORDER BY {by} DESC) AS rnk
                        FROM students{wsql}
                    ) WHERE rnk <= ?
                    ORDER BY stream, value DESC""",
                [*params, limit],
            ).fetchall()]
            title = f"أفضل {limit} في كل شعبة"
        else:
            rows = [dict(r) for r in conn.execute(
                f"""SELECT name, stream, institution, {by} AS value
                    FROM students{wsql}
                    ORDER BY {by} DESC LIMIT ?""",
                [*params, limit],
            ).fetchall()]
            title = f"الأوائل (حسب {'المجموع' if by == 'total' else 'المعدل'})"
    conn.close()

    chart = charts.bar_h(
        [r["name"] for r in rows], [r["value"] for r in rows], title=title
    )
    return {"data": rows, "chart": chart}


@router.get("/remontada")
def remontada(
    limit: int = Query(10, ge=1, le=100),
    stream: str | None = Query(None),
):
    """Biggest comebacks: largest gap between final total and annual average."""
    where, params = ([], [])
    if stream:
        where.append("stream = ?"); params.append(stream)
    where.append("total IS NOT NULL AND moyenne IS NOT NULL")
    wsql = " WHERE " + " AND ".join(where)

    conn = get_connection(read_only=True)
    rows = [dict(r) for r in conn.execute(
        f"""SELECT name, stream, institution,
                   total, moyenne,
                   ROUND(total - moyenne, 2) AS gap
            FROM students{wsql}
            ORDER BY gap DESC LIMIT ?""",
        [*params, limit],
    ).fetchall()]
    conn.close()

    chart = charts.bar_h(
        [r["name"] for r in rows], [r["gap"] for r in rows],
        title="أكبر ريمونتادا (المجموع − المعدل السنوي)",
    )
    return {"data": rows, "chart": chart}
