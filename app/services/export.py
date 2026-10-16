"""Export watchlist to Letterboxd-compatible CSV."""

from __future__ import annotations

import csv
import io

from sqlalchemy.orm import Session

from app.db.models import Film


def export_letterboxd_csv(db: Session) -> str:
    """Build a CSV string importable as a Letterboxd watchlist.

    Includes films that left theaters (``in_theaters=False``) and were marked
    **V** or **?**, excluding those already exported.

    Letterboxd watchlist CSV columns: ``Title, Year``
    """
    films = (
        db.query(Film)
        .filter(Film.in_theaters == False)  # noqa: E712
        .filter(Film.vote.in_(["V", "?"]))
        .filter(Film.exported_at.is_(None))
        .all()
    )

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["Title", "Year"])
    for f in films:
        title = f.tmdb_title or f.raw_title
        writer.writerow([title, f.year or ""])

    return buf.getvalue()

