"""Unit tests for the scrape_all CLI module."""

from __future__ import annotations

import pytest

from app.config import CinemaConfig
from app.scrape_all import scrape_all


@pytest.mark.asyncio
async def test_scrape_all_empty():
    results = await scrape_all(cinemas=[])
    assert results == []


@pytest.mark.asyncio
async def test_scrape_all_stub_cinema():
    cfg = CinemaConfig(
        slug="test-cinema",
        name="Test Cinema",
        url="https://example.com",
        scraper="stub",
    )
    results = await scrape_all(cinemas=[cfg], delay_between_cinemas=0.0)
    assert len(results) == 1
    row = results[0]
    assert row["name"] == "Test Cinema"
    assert row["slug"] == "test-cinema"
    assert row["films"] == 4
    assert row["showtimes"] == 4


@pytest.mark.asyncio
async def test_scrape_all_handles_failure(monkeypatch: pytest.MonkeyPatch):
    from app.scrapers.stub import StubScraper

    async def fail_scrape(self):
        raise RuntimeError("Network down")

    monkeypatch.setattr(StubScraper, "scrape", fail_scrape)

    cfg = CinemaConfig(
        slug="failing-cinema",
        name="Failing Cinema",
        url="https://example.com",
        scraper="stub",
    )
    results = await scrape_all(cinemas=[cfg], delay_between_cinemas=0.0)
    assert len(results) == 1
    assert results[0]["date_range"] == "ERRORE"
    assert results[0]["showtimes"] == 0



@pytest.mark.asyncio
async def test_scrape_all_coming_soon_failure_keeps_the_programme(monkeypatch: pytest.MonkeyPatch):
    from app.scrapers.stub import StubScraper

    async def fail_coming_soon(self):
        raise RuntimeError("prossimamente giù")

    monkeypatch.setattr(StubScraper, "scrape_coming_soon", fail_coming_soon)
    cfg = CinemaConfig(slug="c", name="Cinema", url="https://example.com", scraper="stub")
    row = (await scrape_all(cinemas=[cfg], delay_between_cinemas=0.0))[0]
    assert row["showtimes"] == 4
    assert row["date_range"] != "ERRORE"
    assert row["coming_soon"] == "ERRORE"
