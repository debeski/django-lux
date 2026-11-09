"""Schedules for ``DLUX_TASK_SCHEDULE``: fixed intervals and cron expressions.

An entry has the shape of a ``CELERY_BEAT_SCHEDULE`` entry, so a project moves
one over by copying it::

    from dlux.taskrunner import crontab

    DLUX_TASK_SCHEDULE = {
        "refresh-rates": {"task": "crm.tasks.refresh_rates", "schedule": crontab(minute=0, hour="*/3")},
        "brand-summary": {"task": "documents.tasks.refresh", "schedule": 900},
    }

``schedule`` is seconds, a ``timedelta``, a ``dlux.taskrunner.crontab`` or a
``celery.schedules.crontab`` (read through its expanded fields).
"""

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, time, timedelta

from django.utils import timezone

_DOW_NAMES = {"sun": 0, "mon": 1, "tue": 2, "wed": 3, "thu": 4, "fri": 5, "sat": 6}
_MON_NAMES = {name: index for index, name in enumerate(
    ("jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"), start=1)}


def _expand(spec, low, high, names=None, field=""):
    """``*``, ``*/n``, ``a``, ``a-b``, ``a-b/n`` and comma lists -> a frozenset of ints."""
    if isinstance(spec, int):
        spec = str(spec)
    if isinstance(spec, (set, frozenset, list, tuple)):
        spec = ",".join(str(item) for item in spec)
    values = set()
    for part in str(spec).strip().lower().split(","):
        part = part.strip()
        if not part:
            raise ValueError(f"crontab {field}: empty item in {spec!r}")
        step = 1
        if "/" in part:
            part, step_text = part.split("/", 1)
            step = int(step_text)
            if step < 1:
                raise ValueError(f"crontab {field}: step must be positive in {spec!r}")
        if part == "*":
            start, end = low, high
        elif "-" in part:
            first, last = part.split("-", 1)
            start, end = _number(first, names), _number(last, names)
        else:
            start = _number(part, names)
            end = high if step > 1 else start
        if start > end:
            raise ValueError(f"crontab {field}: {part!r} runs backwards")
        for value in range(start, end + 1, step):
            if field == "day_of_week" and value == 7:
                value = 0
            if not low <= value <= high:
                raise ValueError(f"crontab {field}: {value} is outside {low}-{high}")
            values.add(value)
    return frozenset(values)


def _number(text, names):
    text = text.strip()
    if names and text[:3] in names:
        return names[text[:3]]
    return int(text)


@dataclass(frozen=True)
class crontab:  # noqa: N801 - named like celery.schedules.crontab on purpose
    """Cron schedule in the project's ``TIME_ZONE``; day of month AND day of week must match (as in Celery)."""

    minute: object = "*"
    hour: object = "*"
    day_of_week: object = "*"
    day_of_month: object = "*"
    month_of_year: object = "*"

    def __post_init__(self):
        # Validate eagerly, so a bad setting fails when the worker starts.
        if not all(self.fields):
            raise ValueError(f"crontab {self.describe()} matches nothing")

    @property
    def fields(self):
        return (
            _expand(self.minute, 0, 59, field="minute"),
            _expand(self.hour, 0, 23, field="hour"),
            _expand(self.day_of_week, 0, 7, _DOW_NAMES, field="day_of_week"),
            _expand(self.day_of_month, 1, 31, field="day_of_month"),
            _expand(self.month_of_year, 1, 12, _MON_NAMES, field="month_of_year"),
        )

    def describe(self):
        return f"{self.minute} {self.hour} {self.day_of_month} {self.month_of_year} {self.day_of_week}"

    def next_after(self, moment):
        """The first matching minute strictly after ``moment`` (aware)."""
        minutes, hours, weekdays, monthdays, months = self.fields
        tz = timezone.get_default_timezone()
        local = timezone.localtime(moment, tz).replace(second=0, microsecond=0, tzinfo=None) + timedelta(minutes=1)
        sorted_hours, sorted_minutes = sorted(hours), sorted(minutes)
        day = local.date()
        for _ in range(366 * 5):
            if day.month in months and day.day in monthdays and (day.isoweekday() % 7) in weekdays:
                for hour in sorted_hours:
                    for minute in sorted_minutes:
                        candidate = datetime.combine(day, time(hour, minute))
                        if candidate >= local:
                            return timezone.make_aware(candidate, tz)
            day += timedelta(days=1)
        raise ValueError(f"crontab {self.describe()} never matches")


@dataclass(frozen=True)
class interval:  # noqa: N801
    seconds: float

    def describe(self):
        return f"every {self.seconds:g}s"

    def next_after(self, moment, *, previous_due=None):
        """Next slot on the grid anchored at ``previous_due``, after ``moment``; no catch-up burst."""
        step = timedelta(seconds=self.seconds)
        if previous_due is None or previous_due > moment:
            return moment + step
        missed = int((moment - previous_due) / step) + 1
        return previous_due + step * missed


def as_schedule(value):
    if isinstance(value, (crontab, interval)):
        return value
    if isinstance(value, timedelta):
        value = value.total_seconds()
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if value <= 0:
            raise ValueError("an interval schedule must be positive")
        return interval(float(value))
    if all(hasattr(value, attr) for attr in ("minute", "hour", "day_of_week", "day_of_month", "month_of_year")):
        # celery.schedules.crontab: its attributes are the expanded sets.
        return crontab(
            minute=sorted(value.minute), hour=sorted(value.hour), day_of_week=sorted(value.day_of_week),
            day_of_month=sorted(value.day_of_month), month_of_year=sorted(value.month_of_year),
        )
    if hasattr(value, "run_every"):  # celery.schedules.schedule
        return as_schedule(value.run_every)
    raise ValueError(f"unsupported schedule {value!r}")


@dataclass(frozen=True)
class ScheduleEntry:
    name: str
    task_name: str
    schedule: object
    args: tuple = ()
    kwargs: tuple = ()
    priority: int = 0
    queue_name: str = "default"

    @property
    def signature(self):
        payload = json.dumps(
            [self.task_name, self.schedule.describe(), list(self.args), dict(self.kwargs), self.priority, self.queue_name],
            sort_keys=True, default=str,
        )
        return hashlib.sha256(payload.encode()).hexdigest()

    def first_due(self, now):
        """When a new (or changed) entry first runs: intervals at once, cron at its next match."""
        if isinstance(self.schedule, interval):
            return now
        return self.schedule.next_after(now)

    def next_due(self, now, previous_due=None):
        if isinstance(self.schedule, interval):
            return self.schedule.next_after(now, previous_due=previous_due)
        return self.schedule.next_after(now)


def parse_schedule(raw):
    """``DLUX_TASK_SCHEDULE`` -> ``[ScheduleEntry]``. Raises ``ValueError`` naming the bad entry."""
    entries = []
    for name, spec in (raw or {}).items():
        if not isinstance(spec, dict) or not spec.get("task"):
            raise ValueError(f"DLUX_TASK_SCHEDULE[{name!r}] needs a 'task'.")
        options = spec.get("options") or {}
        priority = options.get("priority", spec.get("priority", 0))
        try:
            schedule = as_schedule(spec.get("schedule"))
        except ValueError as exc:
            raise ValueError(f"DLUX_TASK_SCHEDULE[{name!r}]: {exc}") from exc
        entries.append(ScheduleEntry(
            name=str(name)[:200],
            task_name=str(spec["task"]),
            schedule=schedule,
            args=tuple(spec.get("args") or ()),
            kwargs=tuple(sorted((spec.get("kwargs") or {}).items())),
            priority=int(priority or 0),
            queue_name=str(options.get("queue") or spec.get("queue") or "default"),
        ))
    return entries
