"""Build the phone version of CNV: a static site with the day's data.

GitHub Actions runs the sync every morning, then this command writes ``data.json``
(films, shows, coming soon, cinemas) and copies the web app in ``phone/`` next to it.
The phone does the rest: today's remaining shows, calendar, votes and Letterboxd export.

Usage:
    python -m app.export_static --out site
"""

from __future__ import annotations

import argparse
from datetime import date, datetime, timedelta
import json
from pathlib import Path
import shutil

from sqlalchemy.orm import Session

from app.config import ROOT_DIR, settings
from app.db.engine import SessionLocal, init_db
from app.db.models import Cinema, ComingSoon, Film, Showtime

PHONE_DIR = ROOT_DIR / "phone"
STYLE_CSS = ROOT_DIR / "app" / "web" / "static" / "style.css"
SHOWS_FROM_DAYS_AGO = 1  # yesterday's late shows still belong to last night's programme


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
        }
        for s in db.query(Showtime)
        .filter(Showtime.date >= today - timedelta(days=SHOWS_FROM_DAYS_AGO))
        .order_by(Showtime.date, Showtime.time)
    ]
    coming = [
        {"f": c.film_id, "c": slug_by_id[c.cinema_id], "d": c.release_date.isoformat() if c.release_date else None}
        for c in db.query(ComingSoon)
    ]
    films = [
        {
            "id": f.id,
            "title": f.tmdb_title if f.is_tmdb_confirmed and f.tmdb_title else f.raw_title,
            "tmdb": f.tmdb_id if f.is_tmdb_confirmed else None,
            "poster": f.poster_url if f.is_tmdb_confirmed else None,
            "year": f.year if f.is_tmdb_confirmed else None,
            "status": f.status,
            "event": bool(f.is_event),
            "last_seen": f.last_seen_date.isoformat() if f.last_seen_date else None,
            "left": f.left_theaters_date.isoformat() if f.left_theaters_date else None,
        }
        for f in db.query(Film).order_by(Film.id)
    ]
    return {
        "generated_at": now.isoformat(timespec="minutes"),
        "settings": {
            "days_to_uscito": settings.SYNC_DAYS_TO_USCITO,
            "days_to_uscito_evento": settings.SYNC_DAYS_TO_USCITO_EVENTO,
        },
        "cinemas": [{"slug": c.slug, "name": c.name, "url": c.url} for c in cinemas],
        "films": films,
        "shows": shows,
        "coming": coming,
    }


def build_site(out_dir: Path, data: dict) -> None:
    """Write data.json and the phone app into ``out_dir``."""
    if out_dir.exists():
        shutil.rmtree(out_dir)
    shutil.copytree(PHONE_DIR, out_dir)
    shutil.copy2(STYLE_CSS, out_dir / "style.css")
    (out_dir / "data.json").write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    # A new cache name at every build, so phones pick up the new app files
    sw = out_dir / "sw.js"
    sw.write_text(sw.read_text(encoding="utf-8").replace("__BUILD__", data["generated_at"]), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Costruisce la versione per il telefono di CNV")
    parser.add_argument("--out", default="site", help="cartella di destinazione (default: site)")
    out_dir = Path(parser.parse_args().out)
    init_db()
    with SessionLocal() as db:
        data = build_data(db)
    build_site(out_dir, data)
    print(f"Sito per il telefono in {out_dir}: {len(data['films'])} film, {len(data['shows'])} spettacoli")


if __name__ == "__main__":
    main()
