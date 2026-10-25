"""Tests for backups, the full-sync runner and the daily scheduler."""

from __future__ import annotations

from datetime import datetime, time, timedelta
import sqlite3

import pytest

from app.config import CinemaConfig, settings
from app.db.models import SyncLog
from app.scrapers.base import ShowtimeData
from app.services import runner
from app.services.backup import backup_database, list_backups, sqlite_path
from app.services.runner import SyncAlreadyRunning, last_successful_sync, run_full_sync, utc_now
from app.services.scheduler import needs_catchup, next_run_after

CINEMAS = [CinemaConfig(slug="andromeda", name="Andromeda", url="https://example.com", scraper="stub")]
TODAY = datetime(2026, 10, 23).date()


# ------------------------------------------------------------------
# Backups
# ------------------------------------------------------------------


def test_sqlite_path():
    assert sqlite_path("sqlite:///C:/dati/cnv.db").as_posix() == "C:/dati/cnv.db"
    assert sqlite_path("sqlite:///:memory:") is None
    assert sqlite_path("sqlite://") is None
    assert sqlite_path("postgresql://u:p@localhost/cnv") is None


def test_backup_copies_database_and_keeps_only_the_newest(tmp_path, monkeypatch):
    source = tmp_path / "cnv.db"
    conn = sqlite3.connect(source)
    conn.execute("create table films (title text)")
    conn.execute("insert into films values ('Mammina')")
    conn.commit()
    conn.close()
    backups = tmp_path / "backups"
    backups.mkdir()
    foreign = backups / "cinewatch-manuale.db"  # not made by CNV: never deleted
    foreign.write_text("x")

    stamps = iter(f"2026102{i}-080000" for i in range(5))

    class FakeDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime.strptime(next(stamps), "%Y%m%d-%H%M%S")

    monkeypatch.setattr("app.services.backup.datetime", FakeDatetime)
    made = [backup_database(f"sqlite:///{source.as_posix()}", backups, "test", keep=3) for _ in range(5)]

    kept = list_backups(backups)
    assert [p.name for p in kept] == [m.name for m in reversed(made[2:])]
    assert foreign.exists()
    copy = sqlite3.connect(kept[0])
    assert copy.execute("select title from films").fetchall() == [("Mammina",)]
    copy.close()


def test_backup_skips_missing_or_memory_database(tmp_path):
    assert backup_database("sqlite:///:memory:", tmp_path, "x", 3) is None
    assert backup_database(f"sqlite:///{(tmp_path / 'nope.db').as_posix()}", tmp_path, "x", 3) is None


# ------------------------------------------------------------------
# Runner
# ------------------------------------------------------------------


def shows(day=TODAY):
    return {"andromeda": [ShowtimeData("andromeda", "Clayface", day, time(21, 0))]}


@pytest.mark.asyncio
async def test_run_full_sync_records_a_log(db):
    result, log = await run_full_sync(
        db, "manuale", use_tmdb=False, database_url="sqlite://",
        as_of_date=TODAY, cinemas=CINEMAS, scraper_results=shows(), coming_soon=[],
    )
    assert result.showtimes == 1
    saved = db.query(SyncLog).one()
    assert saved.trigger == "manuale"
    assert saved.ok is True
    assert saved.finished_at is not None
    assert (saved.new_films, saved.showtimes, saved.films_total) == (1, 1, 1)
    assert saved.errors is None
    assert last_successful_sync(db) == saved.started_at


@pytest.mark.asyncio
async def test_run_full_sync_keeps_errors_and_failures(db, monkeypatch):
    _, log = await run_full_sync(
        db, "automatico", use_tmdb=False, database_url="sqlite://",
        as_of_date=TODAY, cinemas=CINEMAS, scraper_results={}, coming_soon=[],
        scraper_errors={"andromeda": RuntimeError("503")},
    )
    assert log.ok is True and log.errors == "andromeda: 503"

    async def boom(*args, **kwargs):
        raise ValueError("rotto")

    monkeypatch.setattr(runner, "run_sync", boom)
    with pytest.raises(ValueError):
        await run_full_sync(db, "manuale", use_tmdb=False, database_url="sqlite://")
    failed = db.query(SyncLog).order_by(SyncLog.id.desc()).first()
    assert failed.ok is False and "rotto" in failed.errors and failed.finished_at is not None


@pytest.mark.asyncio
async def test_only_one_sync_at_a_time(db):
    # A sync started 5 minutes ago in another process and not finished yet
    db.add(SyncLog(trigger="terminale", started_at=utc_now() - timedelta(minutes=5)))
    db.commit()
    with pytest.raises(SyncAlreadyRunning):
        await run_full_sync(db, "manuale", use_tmdb=False, database_url="sqlite://")

    # After 30 minutes it is considered interrupted
    db.query(SyncLog).update({SyncLog.started_at: utc_now() - timedelta(hours=1)})
    db.commit()
    _, log = await run_full_sync(
        db, "manuale", use_tmdb=False, database_url="sqlite://",
        as_of_date=TODAY, cinemas=CINEMAS, scraper_results=shows(), coming_soon=[],
    )
    assert log.ok


# ------------------------------------------------------------------
# Scheduler
# ------------------------------------------------------------------


def test_next_run_after():
    at = time(8, 0)
    assert next_run_after(datetime(2026, 10, 23, 7, 59), at) == datetime(2026, 10, 23, 8, 0)
    assert next_run_after(datetime(2026, 10, 23, 8, 0), at) == datetime(2026, 10, 24, 8, 0)
    assert next_run_after(datetime(2026, 10, 23, 21, 30), at) == datetime(2026, 10, 24, 8, 0)


def test_needs_catchup():
    now = datetime(2026, 10, 23, 21, 0)
    assert needs_catchup(None, now, 20)
    assert needs_catchup(now - timedelta(hours=21), now, 20)
    assert not needs_catchup(now - timedelta(hours=3), now, 20)


def test_settings_defaults():
    assert settings.AUTO_SYNC_TIME == time(8, 0)
    assert settings.BACKUPS_KEEP >= 1


def test_ran_recently():
    from app.services.scheduler import ran_recently

    now = datetime(2026, 10, 23, 8, 0)
    assert ran_recently(now - timedelta(minutes=10), now)  # catch-up at 07:50
    assert not ran_recently(now - timedelta(hours=5), now)
    assert not ran_recently(None, now)


@pytest.mark.asyncio
async def test_daily_sync_is_skipped_right_after_another_one(db, monkeypatch):
    from app.services.scheduler import DailySyncScheduler

    db.add(SyncLog(trigger="automatico", ok=True, started_at=utc_now() - timedelta(minutes=10), finished_at=utc_now()))
    db.commit()

    class SessionFactory:
        def __call__(self):
            return self

        def __enter__(self):
            return db

        def __exit__(self, *exc):
            return False

    scheduler = DailySyncScheduler(SessionFactory(), time(8, 0), 20)
    runs = []

    async def fake_run():
        runs.append("sync")

    monkeypatch.setattr(scheduler, "_run", fake_run)
    assert await scheduler.run_scheduled() is False
    assert runs == []

    db.query(SyncLog).update({SyncLog.started_at: utc_now() - timedelta(hours=10)})
    db.commit()
    assert await scheduler.run_scheduled() is True
    assert runs == ["sync"]
