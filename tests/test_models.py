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
    assert film.vote is None


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


def test_film_vote_values(db):
    film = Film(
        raw_title="Vote Test",
        normalized_title="vote test",
        first_seen=datetime.now(timezone.utc),
        last_seen=datetime.now(timezone.utc),
    )
    db.add(film)
    db.commit()

    for v in ("V", "?"):
        film.vote = v
        db.commit()
        db.refresh(film)
        assert film.vote == v


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




def test_init_db_drops_the_old_x_votes(tmp_path, monkeypatch):
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    import importlib

    engine_module = importlib.import_module("app.db.engine")

    engine = create_engine(f"sqlite:///{(tmp_path / 'vecchio.db').as_posix()}")
    monkeypatch.setattr(engine_module, "engine", engine)
    engine_module.init_db()
    with sessionmaker(bind=engine)() as db:
        for title, vote in (("Voglio", "V"), ("Forse", "?"), ("No", "X")):
            db.add(Film(raw_title=title, normalized_title=title.lower(), vote=vote))
        db.commit()

    engine_module.init_db()  # next start of CNV

    with sessionmaker(bind=engine)() as db:
        assert {f.raw_title: f.vote for f in db.query(Film)} == {"Voglio": "V", "Forse": "?", "No": None}
    engine.dispose()
