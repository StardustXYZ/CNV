"""Coming-soon scraper for cosenzacinema.it (Citrigno, Sale Unical, Italia/Tieri).

The 18tickets pages of these cinemas list only a few presales, while the home page of
cosenzacinema.it has two more sections with what is coming:
- "Eventi & Rassegne": events and film clubs, with the date in the label
  (e.g. "film evento dal 30 ottobre al 1 novembre - cinema unical").
- "Coming soon": upcoming releases, usually without a date.

Every film card names its cinema ("Cinema: Cinema Sale Unical"); the sync maps that
name to a cinema of cinemas.yaml through its aliases. The "In Proiezione" section is
skipped: those films already come with showtimes from 18tickets.
"""

from __future__ import annotations

from datetime import date
import re

from bs4 import BeautifulSoup
import httpx

from app.scrapers.base import ITALIAN_MONTHS, BaseScraper, ComingSoonData, ShowtimeData, nearest_date

DEFAULT_USER_AGENT = "CNV/0.1.0 (+https://github.com/StardustXYZ/CNVTrue; personal cinema tracker)"
DEFAULT_TIMEOUT = 15.0
DEFAULT_URL = "https://cosenzacinema.it/"

COMING_SOON_SECTIONS = ("eventi & rassegne", "coming soon")

_MONTH_NAMES = "|".join(sorted(ITALIAN_MONTHS, key=len, reverse=True))
_LABEL_DATE = re.compile(rf"\b(?P<day>\d{{1,2}})\s+(?P<month>{_MONTH_NAMES})\b", flags=re.IGNORECASE)


def parse_label_date(label: str, reference_date: date) -> date | None:
    """First 'D month' in a card label, e.g. 'rassegna altri sguardi - martedi 27 ottobre'.

    Presale labels ("prevendite aperte dal 5 ottobre") give the start of ticket sales,
    not of the screenings, so they return None. The year is the one that puts the date
    closest to the reference date (in early January "30 dicembre" is last year's).
    """
    if not label or "prevendit" in label.lower():
        return None
    m = _LABEL_DATE.search(label)
    if not m:
        return None
    return nearest_date(int(m.group("day")), ITALIAN_MONTHS[m.group("month").lower()], reference_date)


def _section_of(item) -> str:
    heading = item.find_previous("h2")
    return heading.get_text(" ", strip=True).lower() if heading else ""


def parse_home_html(html: str, reference_date: date | None = None) -> list[ComingSoonData]:
    """Parse the 'Eventi & Rassegne' and 'Coming soon' cards of the cosenzacinema.it home page.

    ``ComingSoonData.cinema`` holds the cinema name printed on the card.
    """
    reference_date = reference_date or date.today()
    soup = BeautifulSoup(html, "html.parser")
    items: list[ComingSoonData] = []

    for card in soup.select(".amy-movie-item"):
        if _section_of(card) not in COMING_SOON_SECTIONS:
            continue
        title_el = card.select_one(".amy-movie-field-title")
        if title_el is None:
            continue
        title = title_el.get_text(" ", strip=True)
        label_el = card.select_one(".amy-movie-field-mpaa")
        label = label_el.get_text(" ", strip=True) if label_el else ""
        cinema_el = card.select_one(".amy-movie-field-cinema .amy-movie-custom-field-content")
        cinema = cinema_el.get_text(" ", strip=True) if cinema_el else ""
        link = title_el.find("a")

        items.append(
            ComingSoonData(
                cinema=cinema,
                raw_title=title,
                release_date=parse_label_date(label, reference_date),
                tags=[label] if label else [],
                source_url=link.get("href", "") if link else "",
            )
        )
    return items


class CosenzaCinemaScraper(BaseScraper):
    """Reads only coming-soon data: showtimes for these cinemas come from 18tickets."""

    def __init__(
        self,
        cinema_slug: str = "cosenzacinema",
        url: str = DEFAULT_URL,
        user_agent: str = DEFAULT_USER_AGENT,
        timeout: float = DEFAULT_TIMEOUT,
    ) -> None:
        super().__init__(cinema_slug, url)
        self.user_agent = user_agent
        self.timeout = timeout

    async def scrape(self) -> list[ShowtimeData]:
        return []

    async def scrape_coming_soon(self) -> list[ComingSoonData]:
        headers = {"User-Agent": self.user_agent}
        async with httpx.AsyncClient(headers=headers, timeout=self.timeout, follow_redirects=True) as client:
            resp = await client.get(self.url)
            resp.raise_for_status()
            return parse_home_html(resp.text)
