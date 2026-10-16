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

