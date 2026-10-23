"""One full sync as run by the CLI, the "Sync" button and the daily scheduler.

Takes a database backup, runs scrapers + TMDB matching, and records a SyncLog row.
Only one sync runs at a time, also across processes (web app and terminal).
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
import logging

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.config import settings
from app.db.models import SyncLog, SyncRun
from app.services.backup import backup_database
from app.services.sync import SyncResult, run_sync
from app.services.tmdb import TmdbClient

logger = logging.getLogger(__name__)

STALE_RUN_AFTER = timedelta(minutes=30)  # an unfinished SyncLog older than this was interrupted
_lock = asyncio.Lock()


class SyncAlreadyRunning(Exception):
    """Another sync is in progress (in this process or in another one)."""


def utc_now() -> datetime:
    """Naive UTC, as SQLite stores and returns datetimes."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _running_elsewhere(db: Session) -> bool:
    return (
        db.query(SyncLog)
        .filter(SyncLog.finished_at.is_(None), SyncLog.started_at > utc_now() - STALE_RUN_AFTER)
        .first()
        is not None
    )


def is_sync_running(db: Session) -> bool:
    return _lock.locked() or _running_elsewhere(db)


def last_successful_sync(db: Session) -> datetime | None:
    """Naive UTC time of the last completed sync (older databases: last successful cinema scrape)."""
    last = db.query(func.max(SyncLog.started_at)).filter(SyncLog.ok.is_(True)).scalar()
    if last is None:
        last = db.query(func.max(SyncRun.created_at)).filter(SyncRun.status == "ok").scalar()
    if isinstance(last, datetime) and last.tzinfo is not None:
        last = last.astimezone(timezone.utc).replace(tzinfo=None)
    return last


async def run_full_sync(
    db: Session,
    trigger: str,
    *,
    use_tmdb: bool = True,
    database_url: str | None = None,
    **sync_kwargs,
) -> tuple[SyncResult, SyncLog]:
    """Back up the database, run the sync and log it.

    ``trigger`` is "manuale", "automatico" or "terminale". Extra keyword arguments go
    to ``run_sync`` (tests use them to inject data). Raises SyncAlreadyRunning.
    """
    if is_sync_running(db):
        raise SyncAlreadyRunning("C'è già un sync in corso")

    async with _lock:
        log = SyncLog(trigger=trigger, started_at=utc_now())
        db.add(log)
        db.commit()
        log_id = log.id
        logger.info("Sync %s avviato", trigger)

        try:
            try:
                backup = backup_database(
                    database_url or settings.DATABASE_URL, settings.BACKUPS_DIR, trigger, settings.BACKUPS_KEEP
                )
            except Exception:
                logger.exception("Backup del database non riuscito: il sync prosegue")
                backup = None

            if use_tmdb and settings.TMDB_API_KEY:
                async with TmdbClient() as tmdb:
                    result = await run_sync(db, matcher=tmdb, **sync_kwargs)
            else:
                result = await run_sync(db, **sync_kwargs)
        except Exception as err:
            db.rollback()
            log = db.get(SyncLog, log_id)
            log.ok = False
            log.errors = f"Sync interrotto: {err.__class__.__name__}: {err}"[:2000]
            log.finished_at = utc_now()
            db.commit()
            logger.exception("Sync %s interrotto", trigger)
            raise

        log = db.get(SyncLog, log_id)
        log.ok = True
        log.finished_at = utc_now()
        log.films_total = result.films
        log.new_films = len(result.new_films)
        log.showtimes = result.showtimes
        log.errors = "\n".join(f"{source}: {err}" for source, err in result.errors.items())[:2000] or None
        log.backup_file = backup.name if backup else None
        db.commit()
        logger.info(
            "Sync %s completato: %d spettacoli, %d film nuovi, %d errori",
            trigger, result.showtimes, len(result.new_films), len(result.errors),
        )
        return result, log
