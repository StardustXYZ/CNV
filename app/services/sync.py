"""Sync service – orchestrates scraping, DB upsert, and in_theaters flag update."""

from __future__ import annotations

import re
import unicodedata
from datetime import date, datetime, timezone

from sqlalchemy.orm import Session

from app.config import CinemaConfig, settings
from app.db.models import Cinema, Film, Showtime
from app.scrapers.base import BaseScraper
from app.scrapers.eighteen_tickets import EighteenTicketsScraper, clean_title
from app.scrapers.garden import CinemaGardenScraper
from app.scrapers.stub import StubScraper

# Registry: maps the ``scraper`` value in cinemas.yaml to its class.
SCRAPER_REGISTRY: dict[str, type[BaseScraper]] = {
    "stub": StubScraper,
    "18tickets": EighteenTicketsScraper,
    "eighteen_tickets": EighteenTicketsScraper,
    "garden": CinemaGardenScraper,
    "cinema_garden": CinemaGardenScraper,
    "cinema-garden": CinemaGardenScraper,
}



def normalize_title(raw: str) -> str:
    """Lowercase, strip accents and punctuation so titles match across sources."""
    t = raw.strip().lower()
    t = unicodedata.normalize("NFKD", t)
    # Remove combining diacritical marks and non-word chars (except spaces)
    t = re.sub(r"[^\w\s]", "", t)
    t = re.sub(r"\s+", " ", t)
    return t.strip()


# ------------------------------------------------------------------
# Internal helpers
# ------------------------------------------------------------------

def _get_or_create_cinema(db: Session, cfg: CinemaConfig) -> Cinema:
    cinema = db.query(Cinema).filter_by(slug=cfg.slug).first()
    if cinema is None:
        cinema = Cinema(slug=cfg.slug, name=cfg.name, url=cfg.url)
        db.add(cinema)
        db.flush()
    return cinema


def _get_or_create_film(db: Session, raw_title: str) -> Film:
    cleaned = clean_title(raw_title)
    norm = normalize_title(cleaned or raw_title)
    film = db.query(Film).filter_by(normalized_title=norm).first()
    if film is None:
        now = datetime.utcnow()
        film = Film(
            raw_title=cleaned or raw_title,
            normalized_title=norm,
            in_theaters=True,
            first_seen=now,
            last_seen=now,
        )
        db.add(film)
        db.flush()
    else:
        film.last_seen = datetime.utcnow()
    return film


# ------------------------------------------------------------------
# Public API
# ------------------------------------------------------------------

async def run_sync(db: Session) -> dict[str, int]:
    """Run all configured scrapers, upsert data, refresh ``in_theaters`` flags.

    Returns a summary dict ``{"films": int, "showtimes": int}``.
    """
    from app.db.engine import init_db
    init_db()

    total_showtimes = 0
    film_ids: set[int] = set()

    for cfg in settings.CINEMAS:
        scraper_cls = SCRAPER_REGISTRY.get(cfg.scraper)
        if scraper_cls is None:
            continue

        scraper = scraper_cls(cinema_slug=cfg.slug, url=cfg.url)
        items = await scraper.scrape()
        cinema = _get_or_create_cinema(db, cfg)

        for item in items:
            film = _get_or_create_film(db, item.raw_title)
            film_ids.add(film.id)

            showtime = Showtime(
                film_id=film.id,
                cinema_id=cinema.id,
                date=item.date,
                time=item.time,
                sala=item.sala,
                tags=",".join(item.tags) if item.tags else None,
                source_url=item.source_url,
                scraped_at=datetime.now(timezone.utc),
            )
            db.add(showtime)
            total_showtimes += 1

    # Refresh the in_theaters flag for every film in the DB
    today = date.today()
    for film in db.query(Film).all():
        film.in_theaters = any(s.date >= today for s in film.showtimes)

    db.commit()
    return {"films": len(film_ids), "showtimes": total_showtimes}

