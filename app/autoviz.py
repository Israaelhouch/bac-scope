"""Rule-based auto-visualization for /ask results.

Looks at the SHAPE of the query result and picks a presentation. Deterministic —
no LLM call. Returns {kind, chart, ...}; `chart` is a full ApexCharts spec
(same format as the REST /stats endpoints) or None when there's nothing to plot.

Decision tree:
  no rows                                  -> empty
  1 row, 1 column                          -> stat   (KPI number)
  1 category + 1 measure
       small integer distribution (<=6)    -> pie
       many rows (>12) or long labels      -> bar (horizontal)
       otherwise                           -> bar (vertical)
  1 category + >=2 measures                -> grouped bar
  2 numeric columns, no category           -> scatter (correlation)
  anything else                            -> table
"""
from __future__ import annotations

from . import charts

LONG_LABEL = 14      # labels longer than this read better horizontally
MAX_PIE = 6          # at most this many slices for a pie
MANY_ROWS = 12       # beyond this, prefer a horizontal bar


def _is_number(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _all_integer(vals) -> bool:
    try:
        return all(float(v).is_integer() for v in vals)
    except (TypeError, ValueError):
        return False


def build(columns: list[str], rows: list[dict]) -> dict:
    if not rows:
        return {"kind": "empty", "chart": None}

    cols = columns or list(rows[0].keys())
    numeric, textual = [], []
    for c in cols:
        vals = [r[c] for r in rows if r[c] is not None]
        (numeric if vals and all(_is_number(v) for v in vals) else textual).append(c)

    # 1) single scalar -> KPI
    if len(rows) == 1 and len(cols) == 1:
        return {"kind": "stat", "label": cols[0], "value": rows[0][cols[0]], "chart": None}

    # 2) one category + one measure
    if len(cols) == 2 and len(textual) == 1 and len(numeric) == 1:
        labels = [r[textual[0]] for r in rows]
        values = [r[numeric[0]] for r in rows]
        nums = [v for v in values if v is not None]
        longest = max((len(str(l)) for l in labels), default=0)

        # small distribution of counts with SHORT labels -> pie
        if (2 <= len(rows) <= MAX_PIE and nums and _all_integer(nums)
                and longest <= LONG_LABEL):
            return {"kind": "pie", "chart": charts.pie(labels, values, "")}
        # long names or many bars -> horizontal
        if len(rows) > MANY_ROWS or longest > LONG_LABEL:
            return {"kind": "bar", "chart": charts.bar_h(labels, values, "")}
        return {"kind": "bar", "chart": charts.bar(labels, values, "")}

    # 3) one category + several measures -> grouped bar
    if len(textual) == 1 and len(numeric) >= 2 and len(rows) <= 40:
        cats = [r[textual[0]] for r in rows]
        series = {col: (cats, [r[col] for r in rows]) for col in numeric}
        return {"kind": "grouped", "chart": charts.grouped_bar(series, "")}

    # 4) two numeric columns, no category -> scatter (correlation)
    if len(numeric) == 2 and not textual and len(rows) > 1:
        xs = [r[numeric[0]] for r in rows]
        ys = [r[numeric[1]] for r in rows]
        return {"kind": "scatter",
                "chart": charts.scatter(xs, ys, numeric[0], numeric[1], "")}

    # 5) fallback
    return {"kind": "table", "chart": None}
