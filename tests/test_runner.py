"""Tests for backups and the full-sync runner."""

from __future__ import annotations

from datetime import datetime, time, timedelta
import sqlite3

import pytest

from app.config import CinemaConfig
from app.db.models import SyncLog
from app.scrapers.base import ShowtimeData
from app.services import runner
from app.services.backup import backup_database, list_backups, sqlite_path
from app.services.runner import SyncAlreadyRunning, run_full_sync, utc_now

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
