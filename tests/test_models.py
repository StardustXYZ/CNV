"""Tests for ORM models."""

from __future__ import annotations

from datetime import date, datetime, time, timezone

from app.db.models import Cinema, Film, Showtime


def test_create_film(db):
    film = Film(
        raw_title="Test Film",
        normalized_title="test film",
        in_theaters=True,
        first_seen=datetime.now(timezone.utc),
        last_seen=datetime.now(timezone.utc),
    )
    db.add(film)
    db.commit()

    assert film.id is not None
    assert film.vote is None
    assert film.in_theaters is True


def test_create_cinema_and_showtime(db):
    cinema = Cinema(slug="test-cinema", name="Test Cinema", url="https://example.com")
    film = Film(
        raw_title="Test",
        normalized_title="test",
        in_theaters=True,
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
        in_theaters=True,
        first_seen=datetime.now(timezone.utc),
        last_seen=datetime.now(timezone.utc),
    )
    db.add(film)
    db.commit()

    for v in ("V", "?", "X"):
        film.vote = v
        db.commit()
        db.refresh(film)
        assert film.vote == v


def test_film_italian_aliases(db):
    film = Film(
        titolo="Il Padrino",
        normalized_title="il padrino",
        anno=1972,
        stato_utente="V",
        stato_programmazione="in_sala",
        data_uscita_dalle_sale=date(2026, 10, 15),
        esportato_letterboxd=True,
    )
    db.add(film)
    db.commit()
    db.refresh(film)

    assert film.raw_title == "Il Padrino"
    assert film.titolo == "Il Padrino"
    assert film.year == 1972
    assert film.anno == 1972
    assert film.vote == "V"
    assert film.stato_utente == "V"
    assert film.status == "in_sala"
    assert film.stato_programmazione == "in_sala"
    assert film.left_theaters_date == date(2026, 10, 15)
    assert film.data_uscita_dalle_sale == date(2026, 10, 15)
    assert film.letterboxd_exported is True
    assert film.esportato_letterboxd is True


def test_daily_snapshot_and_sync_run(db):
    from app.db.models import DailySnapshot, SyncRun

    cinema = Cinema(slug="garden", name="Cinema Garden", url="https://example.com")
    film = Film(titolo="Dune", normalized_title="dune")
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


