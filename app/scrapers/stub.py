"""Stub scraper – returns fake showtime data for development and testing."""

from __future__ import annotations

from datetime import date, time, timedelta

from app.scrapers.base import BaseScraper, ShowtimeData


class StubScraper(BaseScraper):
    """Returns a handful of fake films so the UI is testable without real scraping."""

    async def scrape(self) -> list[ShowtimeData]:
        today = date.today()
        return [
            ShowtimeData(
                cinema=self.cinema_slug,
                raw_title="Il Gladiatore II",
                date=today,
                time=time(20, 30),
                sala="Sala 1",
                tags=["IMAX"],
                source_url=self.url,
            ),
            ShowtimeData(
                cinema=self.cinema_slug,
                raw_title="Parthenope",
                date=today,
                time=time(18, 0),
                sala="Sala 2",
                tags=[],
                source_url=self.url,
            ),
            ShowtimeData(
                cinema=self.cinema_slug,
                raw_title="Conclave",
                date=today + timedelta(days=1),
                time=time(21, 0),
                sala="Sala 3",
                tags=["VO"],
                source_url=self.url,
            ),
            ShowtimeData(
                cinema=self.cinema_slug,
                raw_title="Napoli – New York",
                date=today + timedelta(days=2),
                time=time(17, 30),
                sala="Sala 1",
                tags=[],
                source_url=self.url,
            ),
        ]

