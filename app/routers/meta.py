"""/filters: the selectable values for every filter, so the frontend can
build dropdowns instead of making users type Arabic values by hand.

Supports faceted (cascading) filtering: pass the currently selected filters and
each facet returns only values that still co-exist with the others, so the user
can never pick a combination that yields zero results. Each facet is computed
over all OTHER active filters (standard faceted search), so changing one filter
narrows the rest but never empties its own list.
"""
from __future__ import annotations

from fastapi import APIRouter, Query

from ..db import get_connection

router = APIRouter(tags=["meta"])


def _clause(key: str, value) -> tuple[str, list]:
    if key == "stream":
        return "stream = ?", [value]
    if key == "institution":
        return "institution = ?", [value]
    if key == "mention":
        return "mention = ?", [value]
    if key == "passed":
        return "passed = ?", [1 if value else 0]
    if key == "min_avg":
        return "moyenne >= ?", [value]
    if key == "max_avg":
        return "moyenne <= ?", [value]
    if key == "search":
        return "name LIKE ?", [f"%{value}%"]
    return "", []


def _where(active: dict, exclude: set[str] | None = None) -> tuple[str, list]:
    """Build a WHERE fragment from active filters, skipping excluded keys."""
    exclude = exclude or set()
    clauses, params = [], []
    for key, value in active.items():
        if value is None or value == "" or key in exclude:
            continue
        frag, p = _clause(key, value)
        if frag:
            clauses.append(frag)
            params.extend(p)
    where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
    return where, params


@router.get("/filters")
def get_filters(
    stream: str | None = Query(None),
    institution: str | None = Query(None),
    mention: str | None = Query(None),
    passed: bool | None = Query(None),
    min_avg: float | None = Query(None),
    max_avg: float | None = Query(None),
    search: str | None = Query(None),
):
    """All selectable filter options, narrowed to the current selection."""
    active = {
        "stream": stream, "institution": institution, "mention": mention,
        "passed": passed, "min_avg": min_avg, "max_avg": max_avg, "search": search,
    }
    conn = get_connection(read_only=True)

    def values(column: str, exclude_key: str) -> list[str]:
        where, params = _where(active, exclude={exclude_key})
        rows = conn.execute(
            f"SELECT DISTINCT {column} FROM students{where} ORDER BY {column}", params
        ).fetchall()
        return [r[0] for r in rows if r[0] is not None]

    streams = values("stream", "stream")
    mentions = values("mention", "mention")

    # Institutions: narrow by everything except the institution filter itself.
    inst_where, inst_params = _where(active, exclude={"institution"})
    institutions = [
        {"name": r["institution"], "count": r["n"]}
        for r in conn.execute(
            f"""SELECT institution, COUNT(*) AS n FROM students{inst_where}
                {'AND' if inst_where else 'WHERE'} institution IS NOT NULL
                GROUP BY institution ORDER BY n DESC""",
            inst_params,
        ).fetchall()
    ]

    # Subjects available within the current student selection. The filter columns
    # (stream, institution, mention, passed, moyenne, name) exist only in
    # `students`, so unqualified references resolve to it after the join.
    subj_where, subj_params = _where(active)
    subjects = [
        r[0]
        for r in conn.execute(
            f"""SELECT DISTINCT g.subject
                FROM grades g JOIN students s
                  ON g.registration_number = s.registration_number
                {subj_where}
                ORDER BY g.subject""",
            subj_params,
        ).fetchall()
    ]

    # Average range over everything except the avg filters.
    rng_where, rng_params = _where(active, exclude={"min_avg", "max_avg"})
    rng = conn.execute(
        f"SELECT MIN(moyenne) AS lo, MAX(moyenne) AS hi FROM students{rng_where}",
        rng_params,
    ).fetchone()

    # How many students the full current selection matches.
    tot_where, tot_params = _where(active)
    matching = conn.execute(
        f"SELECT COUNT(*) FROM students{tot_where}", tot_params
    ).fetchone()[0]

    conn.close()
    return {
        "streams": streams,
        "mentions": mentions,
        "institutions": institutions,
        "subjects": subjects,
        "moyenne_range": {"min": rng["lo"], "max": rng["hi"]},
        "passed": [True, False],
        "sort_fields": ["moyenne", "total", "name", "stream", "institution"],
        "matching_count": matching,
    }
