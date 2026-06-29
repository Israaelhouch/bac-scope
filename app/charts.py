"""Full ApexCharts option specs.

Each helper returns a complete ApexCharts configuration object (JSON) that the
frontend renders directly:

    const chart = new ApexCharts(el, spec);  chart.render();

Responses pair this `chart` spec with the raw `data` rows, so the frontend can
also build a table or switch libraries if it ever wants to.
"""
from __future__ import annotations

PALETTE = ["#38bdf8", "#34d399", "#f59e0b", "#f87171", "#a78bfa", "#fb7185", "#22d3ee"]


def bar(x: list, y: list, title: str, y_title: str | None = None) -> dict:
    """Vertical bar (category -> value)."""
    return {
        "chart": {"type": "bar", "height": 330, "toolbar": {"show": False}},
        "series": [{"name": y_title or "القيمة", "data": y}],
        "xaxis": {"categories": x},
        "plotOptions": {"bar": {"borderRadius": 4, "columnWidth": "55%"}},
        "dataLabels": {"enabled": False},
        "colors": [PALETTE[0]],
        "title": {"text": title, "align": "right"},
    }


def bar_h(labels: list, values: list, title: str) -> dict:
    """Horizontal bar — good for ranked name lists."""
    return {
        "chart": {"type": "bar", "height": 360, "toolbar": {"show": False}},
        "series": [{"name": "القيمة", "data": values}],
        "xaxis": {"categories": labels},
        "plotOptions": {"bar": {"horizontal": True, "borderRadius": 4}},
        "dataLabels": {"enabled": True},
        "colors": [PALETTE[0]],
        "title": {"text": title, "align": "right"},
    }


def pie(labels: list, values: list, title: str) -> dict:
    """Pie / donut for a distribution."""
    return {
        "chart": {"type": "donut", "height": 330},
        "series": values,
        "labels": labels,
        "colors": PALETTE,
        "legend": {"position": "bottom"},
        "title": {"text": title, "align": "right"},
    }


def scatter(x: list, y: list, x_title: str, y_title: str, title: str = "") -> dict:
    """Scatter plot for two numeric columns (e.g. annual vs bac average)."""
    return {
        "chart": {"type": "scatter", "height": 340, "zoom": {"enabled": True},
                  "toolbar": {"show": False}},
        "series": [{"name": title or "نقاط", "data": [[a, b] for a, b in zip(x, y)]}],
        "xaxis": {"title": {"text": x_title}, "tickAmount": 8},
        "yaxis": {"title": {"text": y_title}},
        "colors": [PALETTE[0]],
        "title": {"text": title, "align": "right"},
    }


def grouped_bar(series: dict[str, tuple[list, list]], title: str) -> dict:
    """series: {name: (categories, values)} -> grouped vertical bars.

    Categories are taken from the first series (assumed shared).
    """
    categories: list = []
    apex_series = []
    for i, (name, (x, y)) in enumerate(series.items()):
        if not categories:
            categories = x
        apex_series.append({"name": name, "data": y})
    return {
        "chart": {"type": "bar", "height": 360, "toolbar": {"show": False}},
        "series": apex_series,
        "xaxis": {"categories": categories},
        "plotOptions": {"bar": {"borderRadius": 4}},
        "dataLabels": {"enabled": False},
        "colors": PALETTE,
        "title": {"text": title, "align": "right"},
    }
