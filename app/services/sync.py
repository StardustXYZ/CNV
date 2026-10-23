"""Sync service – orchestrates scraping, DB upsert, snapshots, and lifecycle status updates."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
import logging
import re
import unicodedata

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.config import CinemaConfig, settings
from app.db.models import Cinema, DailySnapshot, Film, Showtime, SyncRun
from app.scrapers.base import BaseScraper, CleanedTitle, ShowtimeData, clean_title
from app.scrapers.eighteen_tickets import EighteenTicketsScraper
from app.scrapers.garden import CinemaGardenScraper
from app.scrapers.stub import StubScraper

logger = logging.getLogger(__name__)

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


EVENT_KEYWORDS = ("evento", "film evento", "anteprima")


def is_event_film(film: Film) -> bool:
    """Detect if a film is an event screening (threshold N=3 instead of 7).

    A film is an event only if it has explicit tags or title indicators:
    EVENTO, film evento, ANTEPRIMA.
    """
    if film.is_event:
        return True

    # Check title
    raw_lower = (film.raw_title or "").lower()
    for kw in EVENT_KEYWORDS:
        if kw in raw_lower:
            return True

    # Check showtimes tags
    for s in film.showtimes:
        if s.tags:
            tag_lower = s.tags.lower()
            for kw in EVENT_KEYWORDS:
                if kw in tag_lower:
                    return True

    return False


@dataclass
class SyncChange:
    """Represents a significant change during a sync run."""

    film_id: int
    title: str
    change_type: str  # "new_film", "status_change", "reappeared"
    old_status: str | None = None
    new_status: str | None = None
    details: str = ""


@dataclass
class SyncResult:
    """Summary of a sync execution."""

    films: int = 0
    showtimes: int = 0
    new_films: list[Film] = field(default_factory=list)
    status_changes: list[SyncChange] = field(default_factory=list)
    errors: dict[str, str] = field(default_factory=dict)
    snapshots_created: int = 0
    snapshots_updated: int = 0

    def __getitem__(self, item: str):
        return getattr(self, item)

    def get(self, item: str, default=None):
        return getattr(self, item, default)


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


def _get_or_create_film(db: Session, raw_title: str, today: date | None = None) -> tuple[Film, bool]:
    cleaned = clean_title(raw_title, reference_date=today)
    norm = normalize_title(cleaned or raw_title)
    film = db.query(Film).filter_by(normalized_title=norm).first()
    now = datetime.now(timezone.utc)
    if film is None:
        film = Film(
            raw_title=cleaned or raw_title,
            normalized_title=norm,
            status="in_uscita",
            in_theaters=True,
            first_seen=now,
            last_seen=now,
            last_seen_date=today,
            consecutive_missing_days=0,
        )
        db.add(film)
        db.flush()
        return film, True
    else:
        film.last_seen = now
        if today and (film.last_seen_date is None or today > film.last_seen_date):
            film.last_seen_date = today
        return film, False


# ------------------------------------------------------------------
# Public API
# ------------------------------------------------------------------


async def run_sync(
    db: Session,
    as_of_date: date | None = None,
    cinemas: list[CinemaConfig] | None = None,
    scraper_results: dict[str, list[ShowtimeData]] | None = None,
    scraper_errors: dict[str, Exception] | None = None,
    delay_between_cinemas: float = 0.5,
) -> SyncResult:
    """Run scrapers, update database, record snapshots, and transition film statuses.

    Args:
        db: SQLAlchemy database session.
        as_of_date: Reference current date (defaults to date.today()).
        cinemas: Optional cinema list (defaults to settings.CINEMAS).
        scraper_results: Optional pre-scraped data by cinema slug (used for tests/simulations).
        scraper_errors: Optional injected scraper errors by cinema slug (used for tests).
        delay_between_cinemas: Pause in seconds between cinema requests.

    Returns:
        SyncResult detailing films, showtimes, status changes, and any errors.
    """
    from app.db.engine import init_db

    init_db()

    today = as_of_date or date.today()
    now = datetime.now(timezone.utc)

    target_cinemas = cinemas if cinemas is not None else settings.CINEMAS
    cinema_map: dict[str, Cinema] = {}
    for cfg in target_cinemas:
        cinema_map[cfg.slug] = _get_or_create_cinema(db, cfg)

    scraped_data: dict[str, list[ShowtimeData]] = {}
    failed_cinema_slugs: set[str] = set()
    sync_errors: dict[str, str] = {}

    # 1. Fetch data from scrapers or injected mock data
    for idx, cfg in enumerate(target_cinemas):
        cinema = cinema_map[cfg.slug]

        # Check injected errors
        if scraper_errors and cfg.slug in scraper_errors:
            err_msg = str(scraper_errors[cfg.slug])
            logger.error("Scraper for %s (%s) failed: %s", cfg.name, cfg.slug, err_msg)
            failed_cinema_slugs.add(cfg.slug)
            sync_errors[cfg.slug] = err_msg
            db.add(SyncRun(sync_date=today, cinema_id=cinema.id, status="error", error_message=err_msg, created_at=now))
            continue

        if scraper_results is not None:
            items = scraper_results.get(cfg.slug, [])
        else:
            scraper_cls = SCRAPER_REGISTRY.get(cfg.scraper)
            if scraper_cls is None:
                continue

            if idx > 0 and delay_between_cinemas > 0:
                await asyncio.sleep(delay_between_cinemas)

            try:
                scraper = scraper_cls(cinema_slug=cfg.slug, url=cfg.url)
                items = await scraper.scrape()
            except Exception as err:
                err_msg = str(err)
                logger.error("Scraper for %s (%s) raised exception: %s", cfg.name, cfg.slug, err_msg)
                failed_cinema_slugs.add(cfg.slug)
                sync_errors[cfg.slug] = err_msg
                db.add(SyncRun(sync_date=today, cinema_id=cinema.id, status="error", error_message=err_msg, created_at=now))
                continue

        # Check for anomaly: 0 showtimes returned for a cinema that previously had programming
        prev_shows_count = db.query(Showtime).filter_by(cinema_id=cinema.id).count()
        if len(items) == 0 and prev_shows_count > 0:
            err_msg = f"0 spettacoli restituiti in modo anomalo (precedentemente presenti {prev_shows_count} spettacoli)"
            logger.error("Cinema %s (%s): %s", cfg.name, cfg.slug, err_msg)
            failed_cinema_slugs.add(cfg.slug)
            sync_errors[cfg.slug] = err_msg
            db.add(SyncRun(sync_date=today, cinema_id=cinema.id, status="empty_anomaly", error_message=err_msg, created_at=now))
            continue

        scraped_data[cfg.slug] = items
        db.add(SyncRun(sync_date=today, cinema_id=cinema.id, status="ok", showtimes_count=len(items), created_at=now))

    # 2. Process showtimes for successful scrapers
    seen_film_ids_today: set[int] = set()
    cinema_films_today: dict[int, dict[int, int]] = {}
    new_films: list[Film] = []
    status_changes: list[SyncChange] = []
    total_showtimes_processed = 0

    for slug, items in scraped_data.items():
        cinema = cinema_map[slug]
        if cinema.id not in cinema_films_today:
            cinema_films_today[cinema.id] = {}

        for item in items:
            cleaned = clean_title(item.raw_title, reference_date=today)

            # Purge eventuali spettacoli salvati in precedenza prima di release_from
            if cleaned.release_from:
                norm = normalize_title(cleaned)
                f_existing = db.query(Film).filter_by(normalized_title=norm).first()
                if f_existing:
                    db.query(Showtime).filter(
                        Showtime.film_id == f_existing.id,
                        Showtime.date < cleaned.release_from,
                    ).delete(synchronize_session=False)

            # Scarta spettacoli precedenti a release_from
            if cleaned.release_from and item.date < cleaned.release_from:
                logger.info(
                    "Scartato spettacolo di '%s' al cinema %s del %s (inferiore a release_from: %s)",
                    item.raw_title,
                    slug,
                    item.date,
                    cleaned.release_from,
                )
                continue

            film, is_new = _get_or_create_film(db, item.raw_title, today=today)

            if is_new:
                new_films.append(film)
                status_changes.append(
                    SyncChange(
                        film_id=film.id,
                        title=film.raw_title,
                        change_type="new_film",
                        new_status="in_uscita",
                        details="Nuovo film inserito nel database",
                    )
                )

            # Check if this screening tags the film as an EVENT (EVENTO, film evento, ANTEPRIMA)
            raw_title_low = (item.raw_title or "").lower()
            if any(kw in raw_title_low for kw in ("evento", "anteprima")):
                film.is_event = True
            if item.tags:
                for t in item.tags:
                    t_low = (t or "").lower()
                    if any(kw in t_low for kw in ("evento", "film evento", "anteprima")):
                        film.is_event = True
                        break

            # Upsert showtime
            existing_show = (
                db.query(Showtime)
                .filter_by(
                    film_id=film.id,
                    cinema_id=cinema.id,
                    date=item.date,
                    time=item.time,
                    sala=item.sala,
                )
                .first()
            )
            if existing_show:
                existing_show.last_seen = now
                if item.tags:
                    existing_show.tags = ",".join(item.tags)
                if item.source_url:
                    existing_show.source_url = item.source_url
            else:
                new_show = Showtime(
                    film_id=film.id,
                    cinema_id=cinema.id,
                    date=item.date,
                    time=item.time,
                    sala=item.sala,
                    tags=",".join(item.tags) if item.tags else None,
                    source_url=item.source_url,
                    last_seen=now,
                    scraped_at=now,
                )
                db.add(new_show)

            total_showtimes_processed += 1
            seen_film_ids_today.add(film.id)
            cinema_films_today[cinema.id][film.id] = cinema_films_today[cinema.id].get(film.id, 0) + 1

    db.flush()

    # 3. Record daily snapshots
    snapshots_created = 0
    snapshots_updated = 0
    for cinema_id, film_counts in cinema_films_today.items():
        # Remove stale snapshots for today where the film is no longer present
        existing_snaps = (
            db.query(DailySnapshot)
            .filter_by(sync_date=today, cinema_id=cinema_id)
            .all()
        )
        for snap in existing_snaps:
            if snap.film_id not in film_counts:
                db.delete(snap)

        for film_id, count in film_counts.items():
            existing_snap = (
                db.query(DailySnapshot)
                .filter_by(sync_date=today, cinema_id=cinema_id, film_id=film_id)
                .first()
            )
            if existing_snap:
                if existing_snap.showtimes_count != count:
                    existing_snap.showtimes_count = count
                snapshots_updated += 1
            else:
                db.add(
                    DailySnapshot(
                        sync_date=today,
                        cinema_id=cinema_id,
                        film_id=film_id,
                        showtimes_count=count,
                        created_at=now,
                    )
                )
                snapshots_created += 1

    db.flush()

    # Films protected by a cinema that failed today: those present in that cinema's
    # latest recorded snapshot, i.e. its programming as last seen before the failure.
    # Films that had already left that cinema earlier are not protected.
    protected_film_ids: set[int] = set()
    for slug in failed_cinema_slugs:
        cinema_id = cinema_map[slug].id
        last_snap_date = (
            db.query(func.max(DailySnapshot.sync_date))
            .filter(DailySnapshot.cinema_id == cinema_id, DailySnapshot.sync_date <= today)
            .scalar()
        )
        if last_snap_date is None:
            continue
        protected_film_ids.update(
            film_id
            for (film_id,) in db.query(DailySnapshot.film_id).filter_by(cinema_id=cinema_id, sync_date=last_snap_date)
        )

    # 4. Status Determination for all films
    for film in db.query(Film).all():
        old_status = film.status
        seen_today = film.id in seen_film_ids_today
        is_protected_by_failed_cinema = not seen_today and film.id in protected_film_ids

        # Event threshold
        film_is_event = is_event_film(film)
        threshold = settings.SYNC_DAYS_TO_USCITO_EVENTO if film_is_event else settings.SYNC_DAYS_TO_USCITO

        # Update missing days based on calendar dates (difference between today and last seen date)
        if seen_today:
            film.last_seen_date = today
            film.consecutive_missing_days = 0
        elif is_protected_by_failed_cinema:
            film.last_seen_date = today
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

        # Dates analysis
        all_dates = [s.date for s in film.showtimes]

        if not all_dates:
            target_status = "in_uscita"
        elif min(all_dates) > today:
            # First showtime is in the future
            target_status = "in_uscita"
        else:
            # Has showtimes today or past
            if film.consecutive_missing_days >= threshold:
                target_status = "uscito"
            else:
                # Tolerates gaps: remains in_sala as long as missing < threshold
                target_status = "in_sala"

        # Apply state transitions
        if old_status == "uscito" and target_status == "in_sala":
            # Reappeared after being marked uscito
            film.status = "in_sala"
            film.left_theaters_date = None
            film.in_theaters = True
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
            film.in_theaters = False
            if film.left_theaters_date is None:
                film.left_theaters_date = today
            if old_status != "uscito":
                status_changes.append(
                    SyncChange(
                        film_id=film.id,
                        title=film.raw_title,
                        change_type="status_change",
                        old_status=old_status,
                        new_status="uscito",
                        details=f"Non presente da {film.consecutive_missing_days} giorni (soglia={threshold})",
                    )
                )
        elif target_status == "in_sala":
            film.status = "in_sala"
            film.in_theaters = True
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
            film.in_theaters = True
            film.left_theaters_date = None
            if old_status != "in_uscita":
                status_changes.append(
                    SyncChange(
                        film_id=film.id,
                        title=film.raw_title,
                        change_type="status_change",
                        old_status=old_status,
                        new_status="in_uscita",
                        details="Spettacoli solo futuri (prevendita o correzione data)",
                    )
                )

    db.commit()

    total_films_count = db.query(Film).count()
    return SyncResult(
        films=total_films_count,
        showtimes=total_showtimes_processed,
        new_films=new_films,
        status_changes=status_changes,
        errors=sync_errors,
        snapshots_created=snapshots_created,
        snapshots_updated=snapshots_updated,
    )
