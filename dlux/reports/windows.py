"""Report period maths: window names, bounds, and previous-period offsets."""

from datetime import date, datetime, time, timedelta
from django.utils import timezone

from .config import _reports_config


REPORT_WINDOWS = {"week", "month", "quarter", "half_year", "year", "custom", "all"}


def normalize_report_window(value):
    value = str(value or "week").strip().lower()
    return value if value in REPORT_WINDOWS else "week"


def normalize_backup_window(value):
    """Like normalize_report_window but defaults to 'all' (the historical backup scope)."""
    value = str(value or "all").strip().lower()
    return value if value in REPORT_WINDOWS else "all"


def _parse_report_date(value):
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value or "").strip())
    except (TypeError, ValueError):
        return None


def _week_start_index():
    value = _reports_config().get("week_start", 0)
    try:
        value = int(value)
    except (TypeError, ValueError):
        value = 0
    return value if 0 <= value <= 6 else 0


def get_report_window_bounds(window, *, now=None, custom_start=None, custom_end=None):
    window = normalize_report_window(window)
    if window == "all":
        return None, None
    now = timezone.localtime(now or timezone.now())
    timezone_value = timezone.get_current_timezone()
    if window == "custom":
        start_date = _parse_report_date(custom_start) or now.date()
        end_date = _parse_report_date(custom_end) or start_date
        if end_date < start_date:
            start_date, end_date = end_date, start_date
        start = timezone.make_aware(datetime.combine(start_date, time.min), timezone_value)
        end = timezone.make_aware(datetime.combine(end_date + timedelta(days=1), time.min), timezone_value)
        return start, end
    if window == "year":
        return now.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0), None
    if window == "half_year":
        month = 1 if now.month <= 6 else 7
        return now.replace(month=month, day=1, hour=0, minute=0, second=0, microsecond=0), None
    if window == "quarter":
        month = ((now.month - 1) // 3) * 3 + 1
        return now.replace(month=month, day=1, hour=0, minute=0, second=0, microsecond=0), None
    if window == "month":
        start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        return start, None
    week_start = _week_start_index()
    start_date = now.date() - timedelta(days=(now.weekday() - week_start) % 7)
    start = timezone.make_aware(datetime.combine(start_date, time.min), timezone.get_current_timezone())
    return start, None


def get_previous_period_bounds(window, *, now=None, custom_start=None, custom_end=None):
    now = timezone.localtime(now or timezone.now())
    current_start, current_end = get_report_window_bounds(
        window,
        now=now,
        custom_start=custom_start,
        custom_end=custom_end,
    )
    if current_start is None:
        return None, None
    comparison_end = current_start
    duration = (current_end or now) - current_start
    return comparison_end - duration, comparison_end


def get_previous_week_bounds(*, now=None):
    current_start, _ = get_report_window_bounds("week", now=now)
    previous_start = current_start - timedelta(days=7)
    return previous_start, current_start


def _report_period_details(window, custom_start, custom_end, *, now=None):
    now = timezone.localtime(now or timezone.now())
    errors = []
    parsed_start = _parse_report_date(custom_start)
    parsed_end = _parse_report_date(custom_end)
    if window == "custom":
        if parsed_start is None:
            errors.append("start")
        if parsed_end is None:
            errors.append("end")
        if parsed_start and parsed_end and parsed_end < parsed_start:
            errors.append("order")
        effective_start = parsed_start or now.date()
        effective_end = parsed_end or effective_start
        if effective_end < effective_start:
            effective_start, effective_end = effective_end, effective_start
        custom_start = effective_start.isoformat()
        custom_end = effective_end.isoformat()
    else:
        custom_start = ""
        custom_end = ""
    start, end = get_report_window_bounds(
        window,
        now=now,
        custom_start=custom_start,
        custom_end=custom_end,
    )
    start_label = timezone.localtime(start).date().isoformat() if start else ""
    if end is not None:
        # Custom ranges carry an exclusive upper bound (midnight after the last
        # day), so the inclusive label is the day before it.
        end_label = (timezone.localtime(end).date() - timedelta(days=1)).isoformat()
    elif start is not None:
        # Week/month/quarter/half-year/year are deliberately open-ended: they run
        # from their start through now. Label that end as today so "Active period"
        # reads as the range it filters on rather than a lone start date.
        end_label = now.date().isoformat()
    else:
        end_label = ""
    # En dash rather than an arrow: it carries no direction, so the range reads
    # correctly in both LTR and RTL.
    range_label = f"{start_label} – {end_label}" if end_label and end_label != start_label else start_label
    return {
        "custom_start": custom_start,
        "custom_end": custom_end,
        "start": start,
        "end": end,
        "start_label": start_label,
        "end_label": end_label,
        "range_label": range_label,
        "errors": errors,
    }
