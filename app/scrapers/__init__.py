"""Scrapers package for CNV (Chi Ni Vidimu)."""

from app.scrapers.base import (
    BaseScraper,
    CleanedTitle,
    ComingSoonData,
    ShowtimeData,
    clean_title,
    extract_release_from,
)
from app.scrapers.eighteen_tickets import EighteenTicketsScraper
from app.scrapers.garden import CinemaGardenScraper, GardenScraper
from app.scrapers.stub import StubScraper

__all__ = [
    "BaseScraper",
    "CleanedTitle",
    "ComingSoonData",
    "ShowtimeData",
    "clean_title",
    "extract_release_from",
    "EighteenTicketsScraper",
    "CinemaGardenScraper",
    "GardenScraper",
    "StubScraper",
]
