"""Where each film stands: in sala, in uscita or uscito.

The sync reads the cinemas, then calls ``update_statuses`` to decide, for every film, which
of the three it is today and what changed since the last time. Events (previews, special
screenings) leave the programme sooner, so they use a shorter threshold.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.config import settings
from app.db.models import Cinema, ComingSoon, DailySnapshot, Film


EVENT_KEYWORDS = ("evento", "film evento", "anteprima")
EVENT_WINDOW_DAYS = 14  # shows older than this do not decide whether a film is an event now


def has_event_keyword(text: str | None) -> bool:
    lowered = (text or "").lower()
    return any(kw in lowered for kw in EVENT_KEYWORDS)


def is_event_film(film: Film, today: date | None = None) -> bool:
    """Detect if a film is an event screening (threshold N=3 instead of 7).

    A film is an event only if every one of its current shows is marked EVENTO,
    film evento or ANTEPRIMA: a single preview before a regular run does not make
    the whole film an event. With ``today`` only shows from the last 14 days and the
    future count (falling back to all shows); without it, all shows count.
    """
    shows = list(film.showtimes)
    if today is not None:
        recent = [s for s in shows if s.date >= today - timedelta(days=EVENT_WINDOW_DAYS)]
        shows = recent or shows
    return bool(shows) and all(has_event_keyword(s.tags) for s in shows)


@dataclass
class SyncChange:
    """Represents a significant change during a sync run."""

    film_id: int
    title: str
    change_type: str  # "new_film", "status_change", "reappeared"
    old_status: str | None = None
    new_status: str | None = None
    details: str = ""


def films_kept_by_failed_cinemas(
    db: Session, failed_cinema_slugs: set[str], cinema_map: dict[str, Cinema], today: date
) -> set[int]:
    """Films kept in theaters although their cinema's site failed today."""
    # Films protected by a cinema that failed today: those present in that cinema's
    # latest recorded snapshot, i.e. its programming as last seen before the failure.
    # Films that had already left that cinema earlier are not protected, and the
    # protection ends when the cinema has been failing for longer than the "uscito"
    # threshold: a site broken for good must not keep its films in theaters forever.
    protected_film_ids: set[int] = set()
    for slug in failed_cinema_slugs:
        cinema_id = cinema_map[slug].id
        last_snap_date = (
            db.query(func.max(DailySnapshot.sync_date))
            .filter(DailySnapshot.cinema_id == cinema_id, DailySnapshot.sync_date <= today)
            .scalar()
        )
        if last_snap_date is None or (today - last_snap_date).days > settings.SYNC_DAYS_TO_USCITO:
            continue
        protected_film_ids.update(
            film_id
            for (film_id,) in db.query(DailySnapshot.film_id).filter_by(cinema_id=cinema_id, sync_date=last_snap_date)
        )
    return protected_film_ids


def update_statuses(
    db: Session, today: date, now: datetime, seen_film_ids_today: set[int], protected_film_ids: set[int]
) -> list[SyncChange]:
    """Decide the status of every film and return what changed (the caller commits)."""
    status_changes: list[SyncChange] = []

    announced_film_ids = {film_id for (film_id,) in db.query(ComingSoon.film_id).distinct()}

    # 4. Status Determination for all films
    for film in db.query(Film).all():
        old_status = film.status
        seen_today = film.id in seen_film_ids_today
        is_protected_by_failed_cinema = not seen_today and film.id in protected_film_ids

        # Event threshold, recomputed every sync from the current shows
        film_is_event = is_event_film(film, today=today)
        film.is_event = film_is_event
        threshold = settings.SYNC_DAYS_TO_USCITO_EVENTO if film_is_event else settings.SYNC_DAYS_TO_USCITO

        # Update missing days based on calendar dates (difference between today and last seen date)
        if seen_today:
            film.last_seen_date = today
            film.consecutive_missing_days = 0
        elif is_protected_by_failed_cinema:
            # Not counted as missing, but not seen either: last_seen_date stays the real one
            film.consecutive_missing_days = 0
        else:
            last_d = film.last_seen_date
            if last_d is None:
                snap_date = (
                    db.query(func.max(DailySnapshot.sync_date))
                    .filter(DailySnapshot.film_id == film.id)
                    .scalar()
                )
                last_d = snap_date or (film.last_seen.date() if film.last_seen else today)
                film.last_seen_date = last_d

            days_diff = max(0, (today - last_d).days)
            film.consecutive_missing_days = days_diff

        # Dates analysis: only recent and upcoming shows decide, not those of months ago
        all_dates = [s.date for s in film.showtimes]
        future_dates = [d for d in all_dates if d > today]
        shown_recently = any(today - timedelta(days=threshold) <= d <= today for d in all_dates)

        never_announced_for = 0
        if not all_dates and film.id not in announced_film_ids:
            # Announced but never screened, and no cinema announces it any more: when that
            # lasts as long as the usual threshold, no cinema took it and it leaves too
            last_news = film.last_announced_date or (film.last_seen or film.first_seen or now).date()
            never_announced_for = max(0, (today - last_news).days)

        if not all_dates and never_announced_for >= threshold:
            target_status = "uscito"
        elif not all_dates or (future_dates and not shown_recently):
            # Only future shows: presale, or back in programme after a while
            target_status = "in_uscita"
        elif film.consecutive_missing_days >= threshold:
            # Gone from the programmes, but if a cinema announces it again it is coming back
            target_status = "in_uscita" if film.id in announced_film_ids else "uscito"
        else:
            # Tolerates gaps: remains in_sala as long as missing < threshold
            target_status = "in_sala"

        if target_status != "in_sala":
            # If it comes back to theaters, that is news again (phone notification)
            film.in_sala_pushed = False

        # Apply state transitions
        if old_status == "uscito" and target_status == "in_sala":
            # Reappeared after being marked uscito
            film.status = "in_sala"
            film.left_theaters_date = None
            status_changes.append(
                SyncChange(
                    film_id=film.id,
                    title=film.raw_title,
                    change_type="reappeared",
                    old_status="uscito",
                    new_status="in_sala",
                    details="Film ricomparso in sala (data uscita azzerata)",
                )
            )
        elif target_status == "uscito":
            film.status = "uscito"
            if film.left_theaters_date is None and all_dates:
                # The day of its last screening, not the day CNV noticed (a week later).
                # Never screened: no such day, it never arrived in theaters
                past_dates = [d for d in all_dates if d <= today]
                film.left_theaters_date = max(past_dates, default=film.last_seen_date or today)
            if old_status != "uscito":
                status_changes.append(
                    SyncChange(
                        film_id=film.id,
                        title=film.raw_title,
                        change_type="status_change",
                        old_status=old_status,
                        new_status="uscito",
                        details=(
                            f"Non presente da {film.consecutive_missing_days} giorni (soglia={threshold})"
                            if all_dates
                            else f"Mai arrivato in sala, non più annunciato da {never_announced_for} giorni"
                        ),
                    )
                )
        elif target_status == "in_sala":
            film.status = "in_sala"
            if old_status != "in_sala":
                status_changes.append(
                    SyncChange(
                        film_id=film.id,
                        title=film.raw_title,
                        change_type="status_change",
                        old_status=old_status,
                        new_status="in_sala",
                        details="Film ora in programmazione nelle sale",
                    )
                )
        elif target_status == "in_uscita":
            film.status = "in_uscita"
            film.left_theaters_date = None
            if old_status != "in_uscita":
                status_changes.append(
                    SyncChange(
                        film_id=film.id,
                        title=film.raw_title,
                        change_type="status_change",
                        old_status=old_status,
                        new_status="in_uscita",
                        details=(
                            "Spettacoli solo futuri (prevendita o correzione data)"
                            if all_dates and min(all_dates) > today
                            else f"Torna in programmazione dal {min(future_dates):%d/%m}"
                            if future_dates
                            else "Non più in programmazione ma annunciato di nuovo (prossimamente)"
                        ),
                    )
                )
    return status_changes
