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
    rf"\s*[\(\[]\s*(?:in\s+sala\s+|al\s+cinema\s+|a\s+partire\s+)?\b(?:dall[\'’]\s*|dal\s+|da\s+){_DATE_EXPR}\s*[\)\]]"
    rf"|"
    rf"\s*(?:[-–—:]\s*)?(?:in\s+sala\s+|al\s+cinema\s+|a\s+partire\s+)?\b(?:dall[\'’]\s*|dal\s+){_DATE_EXPR}"
    rf"|"
    rf"\s*[-–—:]\s*(?:in\s+sala\s+|al\s+cinema\s+|a\s+partire\s+)?\bda\s+{_DATE_EXPR}"
    rf")\s*$",
    flags=re.IGNORECASE,
)


ITALIAN_MONTHS: dict[str, int] = {
    "gennaio": 1, "gen": 1,
    "febbraio": 2, "feb": 2,
    "marzo": 3, "mar": 3,
    "aprile": 4, "apr": 4,
    "maggio": 5, "mag": 5,
    "giugno": 6, "giu": 6,
    "luglio": 7, "lug": 7,
    "agosto": 8, "ago": 8,
    "settembre": 9, "set": 9,
    "ottobre": 10, "ott": 10,
    "novembre": 11, "nov": 11,
    "dicembre": 12, "dic": 12,
}

_EXTRACT_DATE_PATTERN = re.compile(
    rf"(?:in\s+sala\s+|al\s+cinema\s+|a\s+partire\s+)?\b(?:dall[\'’]\s*|dal\s+|da\s+)"
    rf"(?:"
    rf"(?P<day_num>\d{{1,2}})[/\-](?P<month_num>\d{{1,2}})(?:[/\-](?P<year_num>\d{{2,4}}))?"
    rf"|"
    rf"(?P<day_word>\d{{1,2}})(?:°)?(?:\s+(?:di\s+)?(?P<month_name>{_MONTHS}))?(?:\s+(?P<year_word>\d{{2,4}}))?"
    rf"|"
    rf"(?P<month_only>{_MONTHS})(?:\s+(?P<year_only>\d{{2,4}}))?"
    rf")",
    flags=re.IGNORECASE,
)


class CleanedTitle(str):
    """String representing the cleaned title with an optional release_from date."""

    title: str
    release_from: date | None

    def __new__(cls, content: str, release_from: date | None = None):
        instance = super().__new__(cls, content)
        instance.title = str(content)
        instance.release_from = release_from
        return instance

    def __repr__(self) -> str:
        if self.release_from:
            return f"CleanedTitle({super().__repr__()}, release_from={self.release_from!r})"
        return super().__repr__()


def _parse_year(raw: str) -> int:
    y = int(raw)
    return 2000 + y if y < 100 else y


def extract_release_from(text: str, reference_date: date | None = None) -> date | None:
    """Extract release date from a trailing phrase like '- DAL 16 DICEMBRE' or '(DAL 16/12)'.

    Only the date suffix at the end of the title is considered, so words inside the
    title such as 'LONTANO DAL MARE' or 'DA 5 BLOODS' are not mistaken for a date.
    """
    if not text:
        return None
    if reference_date is None:
        reference_date = date.today()

    suffix = _DATE_SUFFIX_PATTERN.search(text.strip())
    if not suffix:
        return None
    m = _EXTRACT_DATE_PATTERN.search(suffix.group(0))
    if not m:
        return None

    d = m.groupdict()
    day = 1
    month = reference_date.month
    year: int | None = None  # None: not written, pick the closest one

    if d.get("day_num"):
        day = int(d["day_num"])
        month = int(d["month_num"])
        if d.get("year_num"):
            year = _parse_year(d["year_num"])
    elif d.get("day_word"):
        day = int(d["day_word"])
        if d.get("month_name"):
            month = ITALIAN_MONTHS.get(d["month_name"].lower(), reference_date.month)
        if d.get("year_word"):
            year = _parse_year(d["year_word"])
        elif not d.get("month_name"):
            year = reference_date.year  # "DAL 16": this month
    elif d.get("month_only"):
        month = ITALIAN_MONTHS.get(d["month_only"].lower(), reference_date.month)
        if d.get("year_only"):
            year = _parse_year(d["year_only"])

    if year is None:
        return nearest_date(day, month, reference_date)
    try:
        return date(year, month, day)
    except ValueError:
        return None


def nearest_date(day: int, month: int, reference_date: date) -> date | None:
    """Day and month without a year: the occurrence closest to ``reference_date``.

    On 2 January "30 dicembre" is three days ago, not next December; in October
    "16 dicembre" is this December.
    """
    candidates = []
    for year in (reference_date.year - 1, reference_date.year, reference_date.year + 1):
        try:
            candidates.append(date(year, month, day))
        except ValueError:
            continue
    return min(candidates, key=lambda c: abs((c - reference_date).days), default=None)


def clean_title(title: str, reference_date: date | None = None) -> CleanedTitle:
    """Clean cinema title noise: remove durations, age ratings, event prefixes, hashtags, and date suffixes.

    Extracts 'DAL <data>' into the .release_from property of the returned CleanedTitle.

    Examples:
        - "PRIMETIME (1H50')" -> "PRIMETIME"
        - "14+ MAMMINA" -> "MAMMINA"
        - "EVENTO 8 TRAINSPOTTING 30° ANNIVERSARIO" -> "TRAINSPOTTING 30° ANNIVERSARIO"
        - "#ANTEPRIMA DUNE – PARTE TRE" -> "DUNE – PARTE TRE"
        - "SE AMI QUALCUNO DILLO (1H40')" -> "SE AMI QUALCUNO DILLO"
        - "AVENGERS: DOOMSDAY - DAL 16 DICEMBRE" -> "AVENGERS: DOOMSDAY" (release_from=2026-12-16)
    """
    if not title:
        return CleanedTitle("", None)

    t = title.strip()

    # 1. Remove duration in parentheses, e.g. (1H50'), (1h40m), (2H05'), (90'), (100 min)
    t = re.sub(r"\s*\(\s*\d+\s*[hH]\s*\d*['m]?\s*\)", "", t)
    t = re.sub(r"\s*\(\s*\d+\s*(?:min|minuti|'|m)\s*\)", "", t, flags=re.IGNORECASE)

    # Read the release date from the same suffix that step 2 removes
    release_from = extract_release_from(t, reference_date=reference_date)

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
    return CleanedTitle(t.strip(), release_from=release_from)



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


