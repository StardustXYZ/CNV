"""Offline unit tests for Cinema Garden parser using saved HTML fixtures."""

from __future__ import annotations

from datetime import date, time
from pathlib import Path
import pytest
import httpx

from app.scrapers.garden import (
    CinemaGardenScraper,
    clean_title,
    extract_available_dates,
    extract_current_page_date,
    parse_day_showtimes_html,
    parse_showtimes_html,
)

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture()
def garden_html() -> str:
    return (FIXTURES_DIR / "garden.html").read_text(encoding="utf-8")


@pytest.fixture()
def garden_29_10_html() -> str:
    return (FIXTURES_DIR / "garden_29_10.html").read_text(encoding="utf-8")


def test_garden_schedule(garden_html: str):
    base_url = "https://www.cinemagarden.net/default.aspx"
    items = parse_showtimes_html(garden_html, cinema_slug="Cinema Garden", base_url=base_url)

    # 5 distinct films and 13 total showtimes on the 16/10/2026 schedule
    unique_titles = {clean_title(item.raw_title) for item in items}
    assert len(unique_titles) == 5
    assert unique_titles == {
        "AVENGERS: DOOMSDAY",
        "SE AMI QUALCUNO DILLO",
        "ZUSTISSIA",
        "WHALEFALL - NELLA BALENA",
        "mammina (other mommy)",
    }
    assert len(items) == 13

    # Verify normalization and required fields for every item
    for item in items:
        assert item.cinema == "Cinema Garden"
        assert item.raw_title
        assert isinstance(item.date, date)
        assert item.date == date(2026, 10, 16)
        assert isinstance(item.time, time)
        assert item.sala in ("Sala A", "Sala B", "Sala Garden")
        assert item.source_url.startswith("https://www.cinemagarden.net/sala.aspx?p=")

    # Verify midnight screening (00:01) for Avengers
    avengers_shows = [s for s in items if "AVENGERS" in s.raw_title]
    assert len(avengers_shows) == 4
    midnight_shows = [s for s in avengers_shows if s.time == time(0, 1)]
    assert len(midnight_shows) == 1
    assert midnight_shows[0].sala == "Sala Garden"
    assert midnight_shows[0].source_url == "https://www.cinemagarden.net/sala.aspx?p=3042"

    # Verify dirty title cleanup
    assert avengers_shows[0].raw_title == "AVENGERS: DOOMSDAY - DAL 16 DICEMBRE"
    assert clean_title(avengers_shows[0].raw_title) == "AVENGERS: DOOMSDAY"

    # Verify mammina (other mommy)
    mammina_shows = [s for s in items if "mammina" in s.raw_title]
    assert len(mammina_shows) == 3
    assert mammina_shows[0].source_url == "https://www.cinemagarden.net/sala.aspx?p=3057"
    mammina_times = {s.time for s in mammina_shows}
    assert mammina_times == {time(17, 0), time(19, 30), time(22, 0)}

    # Verify rooms represented
    rooms = {s.sala for s in items}
    assert rooms == {"Sala A", "Sala B", "Sala Garden"}


def test_garden_calendar_dates_extracted(garden_html: str):
    dates = extract_available_dates(garden_html)
    assert len(dates) == 14

    date_objs = [d for d, _ in dates]
    assert date_objs[0] == date(2026, 10, 16)
    assert date_objs[-1] == date(2026, 10, 29)

    # Check URL structure
    assert dates[0][1] == "https://www.cinemagarden.net/default.aspx?data=16-10-2026"
    assert dates[-1][1] == "https://www.cinemagarden.net/default.aspx?data=29-10-2026"


def test_garden_current_page_date_detection(garden_html: str, garden_29_10_html: str):
    d1 = extract_current_page_date(garden_html)
    assert d1 == date(2026, 10, 16)

    d2 = extract_current_page_date(garden_29_10_html, url="https://www.cinemagarden.net/default.aspx?data=29-10-2026")
    assert d2 == date(2026, 10, 29)


def test_garden_29_10_schedule(garden_29_10_html: str):
    items = parse_showtimes_html(
        garden_29_10_html,
        cinema_slug="Cinema Garden",
        base_url="https://www.cinemagarden.net/default.aspx?data=29-10-2026",
    )
    assert len(items) == 4
    for it in items:
        assert it.cinema == "Cinema Garden"
        assert it.date == date(2026, 10, 29)
        assert clean_title(it.raw_title) == "AVENGERS: DOOMSDAY"
        assert it.source_url == "https://www.cinemagarden.net/sala.aspx?p=3042"

    assert any(it.time == time(0, 1) and it.sala == "Sala Garden" for it in items)


@pytest.mark.asyncio
async def test_garden_coming_soon_ignored():
    scraper = CinemaGardenScraper()
    coming_soon = await scraper.scrape_coming_soon()
    assert coming_soon == []


@pytest.mark.asyncio
async def test_garden_scraper_offline_multi_day(monkeypatch: pytest.MonkeyPatch, garden_html: str, garden_29_10_html: str):
    """Test full CinemaGardenScraper.scrape() workflow with mock HTTP responses."""
    def mock_handler(request: httpx.Request) -> httpx.Response:
        url_str = str(request.url)
        if "data=29-10-2026" in url_str:
            return httpx.Response(200, text=garden_29_10_html, request=request)
        # Default home page / other days
        return httpx.Response(200, text=garden_html, request=request)

    mock_transport = httpx.MockTransport(mock_handler)

    # Patch httpx.AsyncClient to use our mock transport and no delay
    orig_async_client = httpx.AsyncClient

    def patched_async_client(*args, **kwargs):
        kwargs["transport"] = mock_transport
        return orig_async_client(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", patched_async_client)

    scraper = CinemaGardenScraper(request_delay=0.0)
    # Scrape runs through home page and available calendar dates
    showtimes = await scraper.scrape()

    assert len(showtimes) > 0
    assert all(s.cinema == "Cinema Garden" for s in showtimes)
    assert any(s.date == date(2026, 10, 16) for s in showtimes)
    assert any(s.date == date(2026, 10, 29) for s in showtimes)

