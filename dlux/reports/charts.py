"""Chart series construction for the overview."""

from ..translations import get_strings


REPORT_CHART_TOP_N = 12


REPORT_CHART_CATEGORICAL_TOP_N = 7


def _chart_series(items, *, limit=REPORT_CHART_TOP_N, other_label=""):
    """Top-N label/count pairs, with the remainder folded into one 'Other' slice."""
    series = [
        {"label": str(item.get("label") or item.get("key") or ""), "count": int(item.get("count") or 0)}
        for item in items
    ]
    if limit and len(series) > limit:
        head = series[:limit]
        remainder = sum(item["count"] for item in series[limit:])
        if remainder:
            head.append({"label": other_label, "count": remainder})
        return head
    return series


def build_report_chart_data(overview, *, strings=None):
    """Chart-ready series for the printable report.

    ``days`` is re-ordered chronologically (the stats query returns newest-first)
    so the trend chart reads left-to-right. The ranked breakdowns are capped at
    ``REPORT_CHART_TOP_N`` so a project with hundreds of models still prints a
    legible chart; the operation mix — the only chart that colours by identity —
    is capped tighter, at the eight validated categorical hue slots.
    """
    strings = strings or get_strings()
    other_label = strings.get("reports_print_other", "Other")
    return {
        "days": [
            {"label": str(item.get("label") or ""), "count": int(item.get("count") or 0)}
            for item in reversed(overview.get("days") or [])
        ],
        "models": _chart_series(overview.get("models") or [], other_label=other_label),
        "actions": _chart_series(
            overview.get("actions") or [],
            limit=REPORT_CHART_CATEGORICAL_TOP_N,
            other_label=other_label,
        ),
        "users": _chart_series(overview.get("users") or [], other_label=other_label),
    }
