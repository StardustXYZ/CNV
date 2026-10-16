"""Scrapers package for CineWatch."""

from app.scrapers.base import BaseScraper, ComingSoonData, ShowtimeData, clean_title
from app.scrapers.eighteen_tickets import EighteenTicketsScraper
from app.scrapers.garden import CinemaGardenScraper, GardenScraper
from app.scrapers.stub import StubScraper

__all__ = [
    "BaseScraper",
    "ComingSoonData",
    "ShowtimeData",
    "clean_title",
    "EighteenTicketsScraper",
    "CinemaGardenScraper",
    "GardenScraper",
    "StubScraper",
]
