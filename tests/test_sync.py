"""Tests for the sync service."""

from __future__ import annotations

import pytest

from app.services.sync import normalize_title



def test_normalize_basic():
    assert normalize_title("  Il Gladiatore II  ") == "il gladiatore ii"


def test_normalize_accents():
    assert normalize_title("Città di Dio") == "citta di dio"


def test_normalize_punctuation():
    assert normalize_title("Napoli – New York") == "napoli new york"


def test_normalize_apostrophe():
    # Apostrophe and similar chars are stripped
    result = normalize_title("L'Amore è Bello")
    assert "lamore" in result
    assert "bello" in result


@pytest.mark.asyncio
async def test_run_sync_with_garden(db, monkeypatch):
    import pytest
    from app.config import CinemaConfig, settings
    from app.services.sync import run_sync
    from app.scrapers.garden import CinemaGardenScraper
    from app.scrapers.base import ShowtimeData
    from datetime import date, time

    fake_shows = [
        ShowtimeData(
            cinema="Cinema Garden",
            raw_title="AVENGERS: DOOMSDAY - DAL 16 DICEMBRE",
            date=date.today(),
            time=time(0, 1),
            sala="Sala Garden",
            tags=[],
            source_url="https://www.cinemagarden.net/sala.aspx?p=3042",
        )
    ]

    monkeypatch.setattr(CinemaGardenScraper, "scrape", lambda self: pytest.helpers.async_return(fake_shows) if hasattr(pytest, "helpers") else _fake_scrape(fake_shows))

    async def _fake_scrape_async():
        return fake_shows

    monkeypatch.setattr(CinemaGardenScraper, "scrape", lambda self: _fake_scrape_async())

    garden_cfg = CinemaConfig(
        slug="garden",
        name="Cinema Garden (Rende)",
        url="https://www.cinemagarden.net/default.aspx",
        scraper="garden",
    )
    monkeypatch.setattr(settings, "CINEMAS", [garden_cfg])

    summary = await run_sync(db)
    assert summary["films"] == 1
    assert summary["showtimes"] == 1

    from app.db.models import Film, Showtime
    film = db.query(Film).first()
    assert film.raw_title == "AVENGERS: DOOMSDAY"
    assert film.normalized_title == "avengers doomsday"
    assert film.in_theaters is True

    showtime = db.query(Showtime).first()
    assert showtime.time == time(0, 1)
    assert showtime.sala == "Sala Garden"


