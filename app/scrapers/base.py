"""Scraper interface – all scrapers must implement BaseScraper."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import date, time


@dataclass
class ShowtimeData:
    """Normalized showtime coming from a scraper."""

    cinema: str  # slug from cinemas.yaml
    raw_title: str  # title exactly as found on the website
    date: date
    time: time
    sala: str | None = None
    tags: list[str] = field(default_factory=list)  # e.g. ["3D", "VO", "ATMOS"]
    source_url: str = ""  # URL of the movie details sheet


@dataclass
class ComingSoonData:
    """Upcoming film without definite showtimes yet."""

    cinema: str  # slug from cinemas.yaml
    raw_title: str  # title as found on the website
    release_date: date | None = None  # release or preview date if known
    tags: list[str] = field(default_factory=list)
    source_url: str = ""  # URL of the movie details sheet


class BaseScraper(ABC):
    """Base class for cinema scrapers.

    Each cinema source in ``config/cinemas.yaml`` maps to a concrete
    subclass via the ``scraper`` field.
    """

    def __init__(self, cinema_slug: str, url: str) -> None:
        self.cinema_slug = cinema_slug
        self.url = url

    @abstractmethod
    async def scrape(self) -> list[ShowtimeData]:
        """Fetch the cinema's website and return normalised showtimes."""
        ...

    async def scrape_coming_soon(self) -> list[ComingSoonData]:
        """Fetch the cinema's coming soon section if available."""
        return []


