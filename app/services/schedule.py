"""Cinema-day rules shared by the sync and the web pages."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta

LATE_SHOW_CUTOFF = time(6, 0)  # shows listed before this hour run after midnight


def programme_day(now: datetime) -> date:
    """The cinema day in progress: until 06:00 it is still the previous evening's programme."""
    return now.date() - timedelta(days=1) if now.time() < LATE_SHOW_CUTOFF else now.date()


def show_datetime(day: date, at: time) -> datetime:
    """Real start of a screening listed under ``day``: shows before 06:00 run after midnight."""
    start = datetime.combine(day, at)
    return start + timedelta(days=1) if at < LATE_SHOW_CUTOFF else start
