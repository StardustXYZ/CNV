"""Build the site of CNV: the app for the browser with the day's data.

GitHub Actions runs the sync every night, then this command writes ``data.json`` (films,
shows, coming soon, cinemas) next to the Flutter app built for the browser
(``mobile/build/web``). The Android app reads the same ``data.json``; the app does the
rest: today's remaining shows, calendar, votes and Letterboxd export.

Usage, after building the app (from mobile/: flutter build web --base-href /CNV/ --pwa-strategy=none):
    python -m app.export_static --out site
"""

from __future__ import annotations

import argparse
from datetime import date, datetime, timedelta
import json
from pathlib import Path
import re
import shutil

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.config import ROOT_DIR, settings
from app.db.engine import SessionLocal, init_db
from app.db.models import Cinema, ComingSoon, Film, FilmMerge, Showtime
from app.services.schedule import SHOW_EXTRA_MINUTES
from app.services.sync import cinemas_not_updated

APP_DIR = ROOT_DIR / "mobile" / "build" / "web"  # the Flutter app built for the browser
SHOWS_FROM_DAYS_AGO = 1  # yesterday's late shows still belong to last night's programme

# How the cinemas mark a show in the original language ("V.O. SOTT.", "V.O.S.", ...) and its age limit
_ORIGINAL_LANGUAGE = re.compile(r"\bV\.?\s?O\.?(?:\s?S\.?|\s+SOTT\.?)?(?!\w)|ORIGINALE|SOTTOTITOL|\bSUB\s?ITA\b|\bENG\b", re.I)
_AGE_LIMIT = re.compile(r"\bV\.?\s?M\.?\s?(\d{1,2})\b|(?<!\d)(\d{1,2})\s?\+")


def show_flags(tags: str | None) -> dict:
    """{"vo": True} for a show in the original language, {"age": 14} with an age limit (only what is set)."""
    flags: dict = {}
    for tag in (tags or "").split(","):
        if _ORIGINAL_LANGUAGE.search(tag):
            flags["vo"] = True
        if match := _AGE_LIMIT.search(tag):
            age = int(match.group(1) or match.group(2))
            flags["age"] = max(age, flags.get("age", 0))
    return flags


def build_data(db: Session, today: date | None = None, now: datetime | None = None) -> dict:
    """Everything the phone app needs, as plain JSON."""
    today = today or date.today()
    now = now or datetime.now().astimezone()
    cinemas = db.query(Cinema).order_by(Cinema.name).all()
    slug_by_id = {c.id: c.slug for c in cinemas}

    shows = [
        {
            "f": s.film_id,
            "c": slug_by_id[s.cinema_id],
            "d": s.date.isoformat(),
            "t": s.time.strftime("%H:%M"),
            "s": s.sala or "",
            "u": s.booking_url or s.source_url or "",
            **show_flags(s.tags),
        }
        for s in db.query(Showtime)
        .filter(Showtime.date >= today - timedelta(days=SHOWS_FROM_DAYS_AGO))
        .order_by(Showtime.date, Showtime.time)
    ]
    announcements = db.query(ComingSoon).all()
    coming = [
        {"f": c.film_id, "c": slug_by_id[c.cinema_id], "d": c.release_date.isoformat() if c.release_date else None}
        for c in announcements
    ]
    pages = _film_pages(db, announcements, slug_by_id, today - timedelta(days=SHOWS_FROM_DAYS_AGO))
    # First day each film was screened here: the phone puts the latest arrivals first
    since = dict(db.query(Showtime.film_id, func.min(Showtime.date)).group_by(Showtime.film_id))
    films = [
        {
            "id": f.id,
            "title": f.tmdb_title if f.is_tmdb_confirmed and f.tmdb_title else f.raw_title,
            "raw": f.raw_title if f.is_tmdb_confirmed and f.tmdb_title and f.tmdb_title != f.raw_title else None,
            "tmdb": f.tmdb_id if f.is_tmdb_confirmed else None,
            "poster": f.poster_url if f.is_tmdb_confirmed else None,
            "year": f.year if f.is_tmdb_confirmed else None,
            "genre": f.genre if f.has_tmdb_details else None,
            "runtime": f.runtime if f.has_tmdb_details else None,
            "plot": f.overview if f.has_tmdb_credits else None,
            "director": f.director if f.has_tmdb_credits else None,
            "cast": f.cast_names if f.has_tmdb_credits else None,
            "status": f.status,
            "event": bool(f.is_event),
            "last_seen": f.last_seen_date.isoformat() if f.last_seen_date else None,
            "left": f.left_theaters_date.isoformat() if f.left_theaters_date else None,
            "since": since[f.id].isoformat() if f.id in since else None,
        }
        for f in db.query(Film).order_by(Film.id)
    ]
    # Merged duplicates (deleted id -> surviving id): the phone moves votes given to the
    # deleted copy. Ids that belong to a film again are left out.
    film_ids = {f["id"] for f in films}
    merged = {
        str(m.old_id): m.new_id
        for m in db.query(FilmMerge)
        if m.old_id not in film_ids and m.new_id in film_ids
    }
    return {
        "generated_at": now.isoformat(timespec="minutes"),
        "settings": {
            "days_to_uscito": settings.SYNC_DAYS_TO_USCITO,
            "days_to_uscito_evento": settings.SYNC_DAYS_TO_USCITO_EVENTO,
            "show_extra_minutes": SHOW_EXTRA_MINUTES,
        },
        "cinemas": [{"slug": c.slug, "name": c.name, "url": c.url} for c in cinemas],
        # Sites that did not answer at the last sync: {slug: last good day or None}
        "not_updated": {c.slug: d.isoformat() if d else None for c, d in cinemas_not_updated(db)},
        "films": films,
        "shows": shows,
        "coming": coming,
        "pages": pages,
        "merged": merged,
    }


def _film_pages(db: Session, announcements: list[ComingSoon], slug_by_id: dict[int, str], since: date) -> list[dict]:
    """The film's page on each cinema's site, for the films it shows or announces.

    The page of its latest show wins; otherwise the announcement on the cinema's own site,
    then one on a shared site (cosenzacinema.it).
    """
    found: dict[tuple[int, int], tuple[int, str]] = {}  # (film, cinema) -> (priority, url)

    def offer(film_id: int, cinema_id: int, priority: int, url: str | None) -> None:
        key = (film_id, cinema_id)
        if url and (key not in found or priority >= found[key][0]):
            found[key] = (priority, url)

    for a in announcements:
        offer(a.film_id, a.cinema_id, 2 if a.source == slug_by_id[a.cinema_id] else 1, a.source_url)
    for s in db.query(Showtime).filter(Showtime.date >= since).order_by(Showtime.date, Showtime.time):
        offer(s.film_id, s.cinema_id, 3, s.source_url)  # in date order: the latest show's page stays
    return [{"f": film_id, "c": slug_by_id[cinema_id], "u": url} for (film_id, cinema_id), (_, url) in sorted(found.items())]


def build_site(out_dir: Path, data: dict, app_dir: Path = APP_DIR) -> None:
    """Write the browser app and data.json into ``out_dir``."""
    if not (app_dir / "index.html").exists():
        raise FileNotFoundError(
            f"Manca l'app per il browser in {app_dir}: da mobile/ esegui prima "
            "flutter build web --base-href /CNV/ --pwa-strategy=none"
        )
    if out_dir.exists():
        shutil.rmtree(out_dir)
    shutil.copytree(app_dir, out_dir)
    (out_dir / "data.json").write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Costruisce il sito di CNV (app per il browser e dati)")
    parser.add_argument("--out", default="site", help="cartella di destinazione (default: site)")
    parser.add_argument("--app", default=str(APP_DIR), help="app Flutter costruita per il browser")
    args = parser.parse_args()
    init_db()
    with SessionLocal() as db:
        data = build_data(db)
    build_site(Path(args.out), data, Path(args.app))
    print(f"Sito di CNV in {args.out}: {len(data['films'])} film, {len(data['shows'])} spettacoli")


if __name__ == "__main__":
    main()
