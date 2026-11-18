"""Tests for ORM models."""

from __future__ import annotations

from datetime import date, datetime, time, timezone

from app.db.models import Cinema, Film, Showtime


def test_create_film(db):
    film = Film(
        raw_title="Test Film",
        normalized_title="test film",
        first_seen=datetime.now(timezone.utc),
        last_seen=datetime.now(timezone.utc),
    )
    db.add(film)
    db.commit()

    assert film.id is not None


def test_create_cinema_and_showtime(db):
    cinema = Cinema(slug="test-cinema", name="Test Cinema", url="https://example.com")
    film = Film(
        raw_title="Test",
        normalized_title="test",
        first_seen=datetime.now(timezone.utc),
        last_seen=datetime.now(timezone.utc),
    )
    db.add_all([cinema, film])
    db.flush()

    showtime = Showtime(
        film_id=film.id,
        cinema_id=cinema.id,
        date=date.today(),
        time=time(20, 0),
        source_url="https://example.com",
        scraped_at=datetime.now(timezone.utc),
    )
    db.add(showtime)
    db.commit()

    assert showtime.id is not None
    assert len(film.showtimes) == 1
    assert film.showtimes[0].cinema.slug == "test-cinema"


def test_daily_snapshot_and_sync_run(db):
    from app.db.models import DailySnapshot, SyncRun

    cinema = Cinema(slug="garden", name="Cinema Garden", url="https://example.com")
    film = Film(raw_title="Dune", normalized_title="dune")
    db.add_all([cinema, film])
    db.flush()

    snapshot = DailySnapshot(
        sync_date=date(2026, 10, 18),
        cinema_id=cinema.id,
        film_id=film.id,
        showtimes_count=3,
    )
    sync_run = SyncRun(
        sync_date=date(2026, 10, 18),
        cinema_id=cinema.id,
        status="ok",
        showtimes_count=3,
    )
    db.add_all([snapshot, sync_run])
    db.commit()

    assert snapshot.id is not None
    assert snapshot.film.raw_title == "Dune"
    assert snapshot.cinema.slug == "garden"
    assert sync_run.status == "ok"




def test_init_db_drops_what_the_removed_local_app_kept(tmp_path, monkeypatch):
    """An old database has NOT NULL columns that new films no longer set: they must go."""
    import importlib
    import sqlite3

    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    engine_module = importlib.import_module("app.db.engine")
    path = tmp_path / "vecchio.db"
    engine = create_engine(f"sqlite:///{path.as_posix()}")
    monkeypatch.setattr(engine_module, "engine", engine)
    engine_module.init_db()  # the current schema...
    with sessionmaker(bind=engine)() as db:
        db.add(Film(raw_title="Dune", normalized_title="dune", status="in_sala"))
        db.commit()
    with engine.begin() as conn:  # ...plus the columns of the old one, filled for the film that is there
        for ddl in (
            "ALTER TABLE films ADD COLUMN vote VARCHAR(1)",
            "ALTER TABLE films ADD COLUMN letterboxd_exported BOOLEAN NOT NULL DEFAULT 0",
            "ALTER TABLE films ADD COLUMN exported_at DATETIME",
            "ALTER TABLE films ADD COLUMN in_sala_noticed BOOLEAN DEFAULT 0",
            "ALTER TABLE films ADD COLUMN seen_on DATE",
            "ALTER TABLE films ADD COLUMN seen_cinema_id INTEGER REFERENCES cinemas(id)",
            "ALTER TABLE films ADD COLUMN diary_exported BOOLEAN DEFAULT 0",
            "UPDATE films SET vote = 'V'",
        ):
            conn.exec_driver_sql(ddl)

    engine_module.init_db()  # next start of CNV

    columns = {row[1] for row in sqlite3.connect(path).execute("PRAGMA table_info(films)")}
    assert not columns & set(engine_module.LEGACY_FILM_COLUMNS)
    with sessionmaker(bind=engine)() as db:
        assert [f.raw_title for f in db.query(Film)] == ["Dune"]  # the film is still there
        db.add(Film(raw_title="Nuovo", normalized_title="nuovo"))  # and new films can be added
        db.commit()
    engine.dispose()
