"""Export the watchlist and the diary of seen films to Letterboxd CSV files, tracking what was exported."""

from __future__ import annotations

import csv
from datetime import datetime, timezone
import io

from sqlalchemy.orm import Session

from app.db.models import Film

WATCHLIST_VOTES = ("V", "?")
CONFIRMED_STATUSES = ("abbinato", "manuale")


def _watchlist_query(db: Session):
    """Films that left theaters and were marked V or ?."""
    return db.query(Film).filter(Film.status == "uscito", Film.vote.in_(WATCHLIST_VOTES))


def exportable_films(db: Session) -> list[Film]:
    """Watchlist films not exported yet and with a confirmed TMDB match (safe to import)."""
    return (
        _watchlist_query(db)
        .filter(
            Film.letterboxd_exported.is_(False),
            Film.tmdb_id.is_not(None),
            Film.tmdb_match_status.in_(CONFIRMED_STATUSES),
        )
        .order_by(Film.left_theaters_date.desc(), Film.raw_title)
        .all()
    )


def films_missing_tmdb(db: Session) -> list[Film]:
    """Watchlist films not exported yet that still need a TMDB match (see "Da verificare")."""
    return [
        f
        for f in _watchlist_query(db).filter(Film.letterboxd_exported.is_(False)).order_by(Film.raw_title)
        if not f.is_tmdb_confirmed
    ]


def exported_films(db: Session) -> list[Film]:
    return (
        _watchlist_query(db)
        .filter(Film.letterboxd_exported.is_(True))
        .order_by(Film.exported_at.desc(), Film.raw_title)
        .all()
    )


def export_letterboxd_csv(db: Session) -> str:
    """CSV for the Letterboxd watchlist import, with columns ``tmdbID, Title, Year``.

    The TMDB id lets Letterboxd pick the exact film, so only confirmed matches are
    included. Exporting does not mark the films: that happens with ``mark_exported``
    once the user has imported the file.
    """
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(["tmdbID", "Title", "Year"])
    for f in exportable_films(db):
        writer.writerow([f.tmdb_id, f.tmdb_title or f.raw_title, f.year or ""])
    return buf.getvalue()


def mark_exported(db: Session, film_ids: list[int]) -> int:
    """Mark films as imported into Letterboxd; returns how many were marked."""
    now = datetime.now(timezone.utc)
    marked = 0
    for film in db.query(Film).filter(Film.id.in_(film_ids)).all():
        if not film.letterboxd_exported:
            film.letterboxd_exported = True
            film.exported_at = now
            marked += 1
    db.flush()
    return marked


def unmark_exported(db: Session, film: Film) -> None:
    """Put a film back among those to export."""
    film.letterboxd_exported = False
    film.exported_at = None
    db.flush()


# ------------------------------------------------------------------ diary (films marked seen, ✓)


def seen_films(db: Session) -> list[Film]:
    """Films marked seen, latest first."""
    films = db.query(Film).filter(Film.vote == "S").all()
    return sorted(films, key=lambda f: (f.seen_on is None, -(f.seen_on.toordinal() if f.seen_on else 0), f.raw_title.lower()))


def diary_exportable(db: Session) -> list[Film]:
    """Seen films not in the Letterboxd diary yet, with a confirmed TMDB match."""
    return [f for f in seen_films(db) if not f.diary_exported and f.is_tmdb_confirmed]


def export_diary_csv(db: Session) -> str:
    """CSV for the Letterboxd import with ``WatchedDate``: each film becomes a diary entry.

    Like the watchlist, exporting marks nothing: ``mark_diary_exported`` does, once imported.
    """
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(["tmdbID", "Title", "Year", "WatchedDate"])
    for f in diary_exportable(db):
        writer.writerow([f.tmdb_id, f.tmdb_title or f.raw_title, f.year or "", f.seen_on.isoformat() if f.seen_on else ""])
    return buf.getvalue()


def mark_diary_exported(db: Session, film_ids: list[int], exported: bool = True) -> None:
    """Mark seen films as imported in the Letterboxd diary (or back to export)."""
    for film in db.query(Film).filter(Film.id.in_(film_ids)).all():
        film.diary_exported = exported
    db.flush()
