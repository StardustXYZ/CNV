"""Sync service – orchestrates scraping, DB upsert, snapshots, and lifecycle status updates."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import date, datetime, time, timezone
import logging
import re

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.config import CinemaConfig, ComingSoonSourceConfig, settings
from app.db.models import Cinema, ComingSoon, DailySnapshot, Film, FilmAlias, FilmMerge, Showtime, SyncRun
from app.scrapers.base import BaseScraper, ComingSoonData, ShowtimeData, clean_title
from app.scrapers.cosenzacinema import CosenzaCinemaScraper
from app.scrapers.eighteen_tickets import EighteenTicketsScraper
from app.scrapers.garden import CinemaGardenScraper
from app.scrapers.stub import StubScraper
from app.services.film_status import SyncChange, films_kept_by_failed_cinemas, has_event_keyword, update_statuses
from app.services.matching import MatchReport, fill_film_details, match_pending_films
from app.services.overrides import apply_overrides
from app.services.schedule import show_datetime
from app.services.tmdb import MovieSearcher
from app.services.titles import normalize_title

logger = logging.getLogger(__name__)

# Registry: maps the ``scraper`` value in cinemas.yaml to its class.
SCRAPER_REGISTRY: dict[str, type[BaseScraper]] = {
    "stub": StubScraper,
    "18tickets": EighteenTicketsScraper,
    "eighteen_tickets": EighteenTicketsScraper,
    "garden": CinemaGardenScraper,
    "cinema_garden": CinemaGardenScraper,
    "cinema-garden": CinemaGardenScraper,
    "cosenzacinema": CosenzaCinemaScraper,
}

# Coming-soon titles that are not films (film-club slots, festival names, ...)
PLACEHOLDER_TITLES = re.compile(
    r"^(?:rassegna|prima visione|film a sorpresa|titolo da definire|da definire)\b", flags=re.IGNORECASE
)


@dataclass
class ComingSoonBatch:
    """The coming-soon list read from one page.

    ``cinema_slug`` is set for a cinema's own page; for multi-cinema sites it is None and
    each item's ``cinema`` holds the cinema name printed on the site.
    """

    source: str
    items: list[ComingSoonData]
    cinema_slug: str | None = None


def is_placeholder_title(raw_title: str) -> bool:
    """True for coming-soon entries that are not films, e.g. "PRIMA VISIONE 2" or "RASSEGNA ALTRI SGUARDI".

    Checked on the title as published: cleaning would turn "PRIMA VISIONE 2" into "2".
    """
    title = raw_title.strip().lstrip("#")
    return not title or bool(PLACEHOLDER_TITLES.match(title))


def _resolve_cinema(name: str, configs: list[CinemaConfig], cinema_map: dict[str, Cinema]) -> Cinema | None:
    """Map a cinema name used by another site to a configured cinema (slug, name or alias)."""
    wanted = normalize_title(name)
    for cfg in configs:
        if wanted in {normalize_title(n) for n in (cfg.slug, cfg.name, *cfg.aliases)}:
            return cinema_map.get(cfg.slug)
    return None


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
    showtimes_removed: int = 0  # cancelled or moved by the cinemas
    matching: MatchReport | None = None  # None when TMDB matching was not run
    coming_soon: dict[str, int] = field(default_factory=dict)  # source -> announced films kept

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


def _find_film(db: Session, norm: str) -> Film | None:
    """Find a film by normalized title, following aliases left by merged duplicates."""
    film = db.query(Film).filter_by(normalized_title=norm).first()
    if film is None:
        alias = db.query(FilmAlias).filter_by(normalized_title=norm).first()
        film = alias.film if alias else None
    return film


def _new_film_id(db: Session) -> int:
    """Id for a new film, never the id of a merged (deleted) one.

    SQLite would reuse the highest id after a merge deleted that film, and a vote kept
    on the phone for the deleted copy would land on an unrelated new film.
    """
    last_film = db.query(func.max(Film.id)).scalar() or 0
    last_merged = db.query(func.max(FilmMerge.old_id)).scalar() or 0
    return max(last_film, last_merged) + 1


def _get_or_create_film(db: Session, raw_title: str, today: date | None = None) -> tuple[Film, bool]:
    cleaned = clean_title(raw_title, reference_date=today)
    norm = normalize_title(cleaned or raw_title)
    film = _find_film(db, norm)
    now = datetime.now(timezone.utc)
    if film is None:
        film = Film(
            id=_new_film_id(db),
            raw_title=cleaned or raw_title,
            normalized_title=norm,
            status="in_uscita",
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


def _remove_cancelled_showtimes(db: Session, cinema_id: int, listed_ids: set[int], local_now: datetime) -> int:
    """Delete this cinema's shows that have not started yet and are no longer on its site.

    Called only after a successful scrape of the cinema: a show missing from the page was
    cancelled or moved (another time or sala). Shows already started stay as history.
    """
    removed = 0
    candidates = db.query(Showtime).filter(Showtime.cinema_id == cinema_id, Showtime.date >= local_now.date())
    for show in candidates.all():
        if show.id not in listed_ids and show_datetime(show.date, show.time) >= local_now:
            db.delete(show)
            removed += 1
    return removed


async def _fetch_coming_soon(
    cinemas: list[CinemaConfig],
    sources: list[ComingSoonSourceConfig],
    delay: float,
) -> tuple[list[ComingSoonBatch], dict[str, str]]:
    """Read the coming-soon pages of each cinema and of the multi-cinema sites.

    A page that fails is reported and left out, so its known releases are kept.
    """
    jobs = [(cfg.slug, cfg.scraper, cfg.url, cfg.slug) for cfg in cinemas]
    jobs += [(src.slug, src.scraper, src.url, None) for src in sources]
    batches: list[ComingSoonBatch] = []
    errors: dict[str, str] = {}
    for source, scraper_name, url, cinema_slug in jobs:
        scraper_cls = SCRAPER_REGISTRY.get(scraper_name)
        if scraper_cls is None:
            continue
        if delay > 0:
            await asyncio.sleep(delay)
        try:
            items = await scraper_cls(cinema_slug=source, url=url).scrape_coming_soon()
        except Exception as err:
            logger.warning("Pagina 'prossimamente' di %s non disponibile: %s", source, err)
            errors[f"{source} (prossimamente)"] = str(err) or err.__class__.__name__
            continue
        batches.append(ComingSoonBatch(source=source, items=items, cinema_slug=cinema_slug))
    return batches, errors


def _apply_coming_soon(
    db: Session,
    batches: list[ComingSoonBatch],
    configs: list[CinemaConfig],
    cinema_map: dict[str, Cinema],
    today: date,
    now: datetime,
) -> tuple[list[Film], dict[str, int]]:
    """Save announced films per cinema; drop announcements a page no longer lists.

    Returns the films created from announcements and the number of entries per source.
    """
    new_films: list[Film] = []
    counts: dict[str, int] = {}
    for batch in batches:
        kept: set[int] = set()
        for item in batch.items:
            if batch.cinema_slug:
                cinema = cinema_map.get(batch.cinema_slug)
            else:
                cinema = _resolve_cinema(item.cinema, configs, cinema_map)
            if cinema is None:
                logger.warning("Cinema '%s' di %s non riconosciuto: aggiungilo agli alias", item.cinema, batch.source)
                continue

            cleaned = clean_title(item.raw_title, reference_date=today)
            if is_placeholder_title(item.raw_title) or not cleaned:
                continue
            norm = normalize_title(cleaned)
            film = _find_film(db, norm)
            if film is None:
                film = Film(
                    id=_new_film_id(db),
                    raw_title=cleaned,
                    normalized_title=norm,
                    status="in_uscita",
                    first_seen=now,
                    last_seen=now,
                    consecutive_missing_days=0,
                )
                db.add(film)
                db.flush()
                new_films.append(film)

            entry = db.query(ComingSoon).filter_by(film_id=film.id, cinema_id=cinema.id, source=batch.source).first()
            release = item.release_date or cleaned.release_from
            if entry is None:
                entry = ComingSoon(film_id=film.id, cinema_id=cinema.id, source=batch.source, first_seen=now)
                db.add(entry)
                entry.release_date = release
            elif entry.id in kept:
                # Same film listed twice on the page (V.O., IMAX, ...): keep the earliest date
                dates = [d for d in (entry.release_date, release) if d]
                entry.release_date = min(dates) if dates else None
            else:
                entry.release_date = release
            entry.tags = ", ".join(item.tags)[:200] or None
            entry.source_url = item.source_url or ""
            entry.last_seen = now
            film.last_announced_date = today
            db.flush()
            kept.add(entry.id)

        stale = db.query(ComingSoon).filter(ComingSoon.source == batch.source)
        if kept:
            stale = stale.filter(ComingSoon.id.notin_(kept))
        for entry in stale.all():
            db.delete(entry)
        counts[batch.source] = len(kept)
    db.flush()
    return new_films, counts


# ------------------------------------------------------------------
# Public API
# ------------------------------------------------------------------


async def _read_programmes(
    target_cinemas: list[CinemaConfig],
    scraper_results: dict[str, list[ShowtimeData]] | None,
    scraper_errors: dict[str, Exception] | None,
    delay_between_cinemas: float,
) -> tuple[dict[str, list[ShowtimeData]], dict[str, str]]:
    """Network: read every cinema's programme (no database writes while waiting).

    Returns the shows by cinema slug and the error message of each cinema that failed.
    """
    fetched: dict[str, list[ShowtimeData]] = {}
    fetch_errors: dict[str, str] = {}
    for idx, cfg in enumerate(target_cinemas):
        if scraper_errors and cfg.slug in scraper_errors:
            fetch_errors[cfg.slug] = str(scraper_errors[cfg.slug])
            continue
        if scraper_results is not None:
            fetched[cfg.slug] = scraper_results.get(cfg.slug, [])
            continue

        scraper_cls = SCRAPER_REGISTRY.get(cfg.scraper)
        if scraper_cls is None:
            # Misconfiguration: treat like a failed scraper so its films are not considered missing
            fetch_errors[cfg.slug] = f"Scraper sconosciuto '{cfg.scraper}' in cinemas.yaml"
            continue
        if idx > 0 and delay_between_cinemas > 0:
            await asyncio.sleep(delay_between_cinemas)
        try:
            fetched[cfg.slug] = await scraper_cls(cinema_slug=cfg.slug, url=cfg.url).scrape()
        except Exception as err:
            fetch_errors[cfg.slug] = str(err) or err.__class__.__name__
    return fetched, fetch_errors


def _judge_cinemas(
    db: Session,
    target_cinemas: list[CinemaConfig],
    cinema_map: dict[str, Cinema],
    fetched: dict[str, list[ShowtimeData]],
    fetch_errors: dict[str, str],
    today: date,
    now: datetime,
    local_now: datetime,
) -> tuple[dict[str, list[ShowtimeData]], set[str], dict[str, str]]:
    """Record how each cinema went. Returns the shows of the cinemas that can be trusted,
    the slugs of those that failed (their films are protected) and the errors by slug."""
    scraped_data: dict[str, list[ShowtimeData]] = {}
    failed_cinema_slugs: set[str] = set()
    sync_errors: dict[str, str] = {}

    for cfg in target_cinemas:
        cinema = cinema_map[cfg.slug]
        if cfg.slug in fetch_errors:
            err_msg = fetch_errors[cfg.slug]
            logger.error("Scraper for %s (%s) failed: %s", cfg.name, cfg.slug, err_msg)
            failed_cinema_slugs.add(cfg.slug)
            sync_errors[cfg.slug] = err_msg
            db.add(SyncRun(sync_date=today, cinema_id=cinema.id, status="error", error_message=err_msg, created_at=now))
            continue

        items = fetched[cfg.slug]
        # Anomaly: 0 showtimes from a cinema that had shows still to come. A cinema with
        # no upcoming shows that returns 0 is simply closed (e.g. summer), not broken.
        upcoming_count = (
            sum(
                1
                for show in db.query(Showtime).filter(Showtime.cinema_id == cinema.id, Showtime.date >= local_now.date())
                if show_datetime(show.date, show.time) >= local_now
            )
            if not items
            else 0
        )
        if upcoming_count:
            err_msg = f"0 spettacoli restituiti in modo anomalo (ne erano in programma {upcoming_count})"
            logger.error("Cinema %s (%s): %s", cfg.name, cfg.slug, err_msg)
            failed_cinema_slugs.add(cfg.slug)
            sync_errors[cfg.slug] = err_msg
            db.add(SyncRun(sync_date=today, cinema_id=cinema.id, status="empty_anomaly", error_message=err_msg, created_at=now))
            continue

        scraped_data[cfg.slug] = items
        db.add(SyncRun(sync_date=today, cinema_id=cinema.id, status="ok", showtimes_count=len(items), created_at=now))
    return scraped_data, failed_cinema_slugs, sync_errors


@dataclass
class StoredShows:
    """What storing the day's shows produced."""

    seen_film_ids: set[int]
    cinema_films: dict[int, dict[int, int]]  # cinema id -> film id -> number of shows today
    new_films: list[Film]
    changes: list[SyncChange]
    processed: int
    removed: int


def _store_showtimes(
    db: Session,
    scraped_data: dict[str, list[ShowtimeData]],
    cinema_map: dict[str, Cinema],
    today: date,
    now: datetime,
    local_now: datetime,
) -> StoredShows:
    """Create or refresh the shows read today, and drop those the cinemas took off."""
    seen_film_ids_today: set[int] = set()
    cinema_films_today: dict[int, dict[int, int]] = {}
    new_films: list[Film] = []
    status_changes: list[SyncChange] = []
    total_showtimes_processed = 0
    showtimes_removed = 0

    for slug, items in scraped_data.items():
        cinema = cinema_map[slug]
        if cinema.id not in cinema_films_today:
            cinema_films_today[cinema.id] = {}
        listed_shows: list[Showtime] = []  # shows on the cinema's page right now

        for item in items:
            cleaned = clean_title(item.raw_title, reference_date=today)

            # Purge eventuali spettacoli salvati in precedenza prima di release_from.
            # Solo per questo cinema: la data "DAL ..." scritta da un cinema non vale per gli
            # altri (es. un'anteprima del 15/12 altrove deve restare).
            if cleaned.release_from:
                f_existing = _find_film(db, normalize_title(cleaned))
                if f_existing:
                    db.query(Showtime).filter(
                        Showtime.film_id == f_existing.id,
                        Showtime.cinema_id == cinema.id,
                        Showtime.date < cleaned.release_from,
                    ).delete(synchronize_session=False)

            # Scarta spettacoli precedenti a release_from
            if cleaned.release_from and item.date < cleaned.release_from:
                logger.debug(
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

            # Tags of this screening. An event written only in the title ("EVENTO 8 ...")
            # becomes a tag too: whether the film is an event is decided from its shows.
            show_tags = [t for t in item.tags if t]
            if has_event_keyword(item.raw_title) and not any(has_event_keyword(t) for t in show_tags):
                show_tags.append("EVENTO")

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
                existing_show.tags = ",".join(show_tags) or None
                if item.source_url:
                    existing_show.source_url = item.source_url
                existing_show.booking_url = item.booking_url or None
                listed_shows.append(existing_show)
            else:
                new_show = Showtime(
                    film_id=film.id,
                    cinema_id=cinema.id,
                    date=item.date,
                    time=item.time,
                    sala=item.sala,
                    tags=",".join(show_tags) or None,
                    source_url=item.source_url,
                    booking_url=item.booking_url or None,
                    last_seen=now,
                    scraped_at=now,
                )
                db.add(new_show)
                listed_shows.append(new_show)

            total_showtimes_processed += 1
            seen_film_ids_today.add(film.id)
            cinema_films_today[cinema.id][film.id] = cinema_films_today[cinema.id].get(film.id, 0) + 1

        db.flush()
        showtimes_removed += _remove_cancelled_showtimes(
            db, cinema.id, {show.id for show in listed_shows}, local_now
        )
    db.flush()
    return StoredShows(
        seen_film_ids=seen_film_ids_today,
        cinema_films=cinema_films_today,
        new_films=new_films,
        changes=status_changes,
        processed=total_showtimes_processed,
        removed=showtimes_removed,
    )


def _record_snapshots(
    db: Session, cinema_films_today: dict[int, dict[int, int]], today: date, now: datetime
) -> tuple[int, int]:
    """Daily snapshots of what each cinema shows. Returns how many were created and updated."""
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
    return snapshots_created, snapshots_updated


async def run_sync(
    db: Session,
    as_of_date: date | None = None,
    cinemas: list[CinemaConfig] | None = None,
    scraper_results: dict[str, list[ShowtimeData]] | None = None,
    scraper_errors: dict[str, Exception] | None = None,
    delay_between_cinemas: float = 0.5,
    matcher: MovieSearcher | None = None,
    coming_soon: list[ComingSoonBatch] | None = None,
    coming_soon_sources: list[ComingSoonSourceConfig] | None = None,
    local_now: datetime | None = None,
) -> SyncResult:
    """Run scrapers, update database, record snapshots, and transition film statuses.

    All the websites are read first and the database is written only afterwards, in a
    short transaction: while the sync waits on the network the database stays free for other writers.

    Args:
        db: SQLAlchemy database session.
        as_of_date: Reference current date (defaults to date.today()).
        cinemas: Optional cinema list (defaults to settings.CINEMAS).
        scraper_results: Optional pre-scraped data by cinema slug (used for tests/simulations).
        scraper_errors: Optional injected scraper errors by cinema slug (used for tests).
        delay_between_cinemas: Pause in seconds between cinema requests.
        matcher: TMDB searcher (e.g. TmdbClient). When given, films not yet checked are
            matched to TMDB and duplicates with the same TMDB id are merged.
        coming_soon: Pre-read coming-soon lists (tests). When None they are fetched live,
            but only if showtimes are fetched live too (``scraper_results`` is None).
        coming_soon_sources: Multi-cinema coming-soon sites. Default: those in
            cinemas.yaml when using the configured cinemas, none for a custom cinema list.
        local_now: Local time used to tell started shows from upcoming ones. Default: now,
            or the start of ``as_of_date`` when simulating another day.

    Returns:
        SyncResult detailing films, showtimes, status changes, and any errors.
    """
    today = as_of_date or date.today()
    now = datetime.now(timezone.utc)
    if local_now is None:
        local_now = datetime.now() if today == date.today() else datetime.combine(today, time.min)

    target_cinemas = cinemas if cinemas is not None else settings.CINEMAS

    # 1. Network: the cinemas' programmes
    fetched, fetch_errors = await _read_programmes(target_cinemas, scraper_results, scraper_errors, delay_between_cinemas)

    # 1b. Network: coming-soon pages ("prossimamente") of each cinema and of multi-cinema sites
    coming_errors: dict[str, str] = {}
    if coming_soon is None and scraper_results is None:
        if coming_soon_sources is None:
            coming_soon_sources = settings.COMING_SOON_SOURCES if cinemas is None else []
        coming_soon, coming_errors = await _fetch_coming_soon(
            target_cinemas, coming_soon_sources, delay_between_cinemas
        )

    # From here on: database only
    cinema_map: dict[str, Cinema] = {}
    for cfg in target_cinemas:
        cinema_map[cfg.slug] = _get_or_create_cinema(db, cfg)

    scraped_data, failed_cinema_slugs, sync_errors = _judge_cinemas(
        db, target_cinemas, cinema_map, fetched, fetch_errors, today, now, local_now
    )
    sync_errors.update(coming_errors)

    # 2. Process showtimes for successful scrapers
    stored = _store_showtimes(db, scraped_data, cinema_map, today, now, local_now)
    seen_film_ids_today = stored.seen_film_ids
    new_films = stored.new_films
    status_changes = stored.changes

    # 2b. Announced films: entries per cinema, new films for titles never seen
    coming_counts: dict[str, int] = {}
    if coming_soon:
        announced, coming_counts = _apply_coming_soon(db, coming_soon, target_cinemas, cinema_map, today, now)
        for film in announced:
            new_films.append(film)
            status_changes.append(
                SyncChange(
                    film_id=film.id,
                    title=film.raw_title,
                    change_type="new_film",
                    new_status="in_uscita",
                    details="Nuovo film annunciato (prossimamente)",
                )
            )

    # 3. Record daily snapshots
    snapshots_created, snapshots_updated = _record_snapshots(db, stored.cinema_films, today, now)

    # 3b. TMDB matching: link new films to TMDB and merge duplicates before computing statuses
    match_report: MatchReport | None = None
    if matcher is not None:
        new_film_ids = [f.id for f in new_films]
        # Save before talking to TMDB: the database must not stay locked during the requests
        db.commit()
        match_report = await match_pending_films(db, matcher, today=today)
        await apply_overrides(db, matcher, report=match_report)  # matches chosen by hand (config/abbinamenti.yaml)
        if hasattr(matcher, "get_movie"):
            # Runtime and genre, for the end time of the shows
            match_report.details_filled = await fill_film_details(db, matcher, match_report)
        merges = match_report.merges
        if merges:
            seen_film_ids_today = {merges.get(fid, fid) for fid in seen_film_ids_today}
            new_films = [f for f, fid in zip(new_films, new_film_ids) if fid not in merges]
            status_changes = [c for c in status_changes if c.film_id not in merges]

    # 4. Status determination for all films
    protected_ids = films_kept_by_failed_cinemas(db, failed_cinema_slugs, cinema_map, today)
    status_changes += update_statuses(db, today, now, seen_film_ids_today, protected_ids)

    db.commit()

    total_films_count = db.query(Film).count()
    return SyncResult(
        films=total_films_count,
        showtimes=stored.processed,
        new_films=new_films,
        status_changes=status_changes,
        errors=sync_errors,
        snapshots_created=snapshots_created,
        snapshots_updated=snapshots_updated,
        showtimes_removed=stored.removed,
        matching=match_report,
        coming_soon=coming_counts,
    )


def cinemas_not_updated(db: Session) -> list[tuple[Cinema, date | None]]:
    """Cinemas whose site failed at the last sync, with the day of their last good one.

    Their shows are the ones read that day and may have changed since.
    """
    result = []
    for cinema in db.query(Cinema).order_by(Cinema.name):
        last = db.query(SyncRun).filter_by(cinema_id=cinema.id).order_by(SyncRun.created_at.desc(), SyncRun.id.desc()).first()
        if last is None or last.status == "ok":
            continue
        last_ok = (
            db.query(func.max(SyncRun.sync_date)).filter(SyncRun.cinema_id == cinema.id, SyncRun.status == "ok").scalar()
        )
        result.append((cinema, last_ok))
    return result
