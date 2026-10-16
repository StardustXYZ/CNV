"""Scraper interface – all scrapers must implement BaseScraper."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import date, time
import re

_MONTHS = (
    r"(?:gennaio|febbraio|marzo|aprile|maggio|giugno|luglio|agosto|settembre|ottobre|novembre|dicembre"
    r"|gen|feb|mar|apr|mag|giu|lug|ago|set|ott|nov|dic)"
)

_DATE_EXPR = (
    r"(?:"
    r"\d{1,2}[/\-]\d{1,2}(?:[/\-]\d{2,4})?"
    rf"|\d{{1,2}}(?:°)?(?:\s+(?:di\s+)?{_MONTHS})?(?:\s+\d{{2,4}})?"
    rf"|{_MONTHS}(?:\s+\d{{2,4}})?"
    r")"
)

_DATE_SUFFIX_PATTERN = re.compile(
    rf"(?:"
    rf"\s*[\(\[]\s*(?:in\s+sala\s+|al\s+cinema\s+|a\s+partire\s+)?(?:dall[\'’]\s*|dal\s+|da\s+){_DATE_EXPR}\s*[\)\]]"
    rf"|"
    rf"\s*(?:[-–—:]\s*)?(?:in\s+sala\s+|al\s+cinema\s+|a\s+partire\s+)?(?:dall[\'’]\s*|dal\s+){_DATE_EXPR}"
    rf"|"
    rf"\s*[-–—:]\s*(?:in\s+sala\s+|al\s+cinema\s+|a\s+partire\s+)?da\s+{_DATE_EXPR}"
    rf")\s*$",
    flags=re.IGNORECASE,
)


def clean_title(title: str) -> str:
    """Clean cinema title noise: remove durations, age ratings, event prefixes, hashtags, and date suffixes.

    Examples:
        - "PRIMETIME (1H50')" -> "PRIMETIME"
        - "14+ MAMMINA" -> "MAMMINA"
        - "EVENTO 8 TRAINSPOTTING 30° ANNIVERSARIO" -> "TRAINSPOTTING 30° ANNIVERSARIO"
        - "#ANTEPRIMA DUNE – PARTE TRE" -> "DUNE – PARTE TRE"
        - "SE AMI QUALCUNO DILLO (1H40')" -> "SE AMI QUALCUNO DILLO"
        - "AVENGERS: DOOMSDAY - DAL 16 DICEMBRE" -> "AVENGERS: DOOMSDAY"
    """
    if not title:
        return ""

    t = title.strip()

    # 1. Remove duration in parentheses, e.g. (1H50'), (1h40m), (2H05'), (90'), (100 min)
    t = re.sub(r"\s*\(\s*\d+\s*[hH]\s*\d*['m]?\s*\)", "", t)
    t = re.sub(r"\s*\(\s*\d+\s*(?:min|minuti|'|m)\s*\)", "", t, flags=re.IGNORECASE)

    # 2. Remove date suffixes: e.g. "- DAL 16 DICEMBRE", "- DAL 16/12", "(DAL 16 DICEMBRE)"
    t = _DATE_SUFFIX_PATTERN.sub("", t).strip()

    # 3. Iteratively strip prefixes: hashtags, age ratings, events, anteprima/prima visione
    prefix_patterns = [
        # Hashtags like #ANTEPRIMA, #EVENTO, #SPECIAL
        r"^#\w+\s*[-:–—]?\s*",
        # Age ratings: 14+, 18+, 6+, VM14, VM18, VM 14+, etc.
        r"^(?:(?:VM\s*)?\d+\s*\+|\bVM\s*(?:14|18|6|12)\b)\s*[-:–—]?\s*",
        # Event: EVENTO 8, EVENTO 10, EVENTO € 8.00, EVENTO
        r"^EVENTO(?:\s+(?:€\s*)?[\d\.,]+)?\s*[-:–—]?\s*",
        # PRIMA VISIONE, ANTEPRIMA without hashtag
        r"^(?:PRIMA\s+VISIONE|ANTEPRIMA)\s*[-:–—]?\s*",
    ]

    changed = True
    while changed:
        changed = False
        for pat in prefix_patterns:
            new_t = re.sub(pat, "", t, flags=re.IGNORECASE).strip()
            if new_t != t:
                t = new_t
                changed = True

    # 4. In case a prefix removal revealed another date suffix
    t = _DATE_SUFFIX_PATTERN.sub("", t).strip()

    # 5. Strip any leftover leading or trailing separators (dashes, colons)
    t = re.sub(r"^[-:–—\s]+|[-:–—\s]+$", "", t)
    return t.strip()



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


