"""Scraper for Cinema Garden (Rende): https://www.cinemagarden.net/default.aspx

The site is built on ASP.NET:
- The daily schedule is fetched with the query parameter ?data=DD-MM-YYYY (e.g. ?data=16-10-2026).
- The home page displays date links for the next ~14 days.
- Each movie details card has a link to sala.aspx?p=ID.
- Each movie card lists showtimes with hall/room (Sala A, Sala B, Sala Garden) and anyticket.it booking links.
- The "Prossimamente" section only has posters without text or dates: titles are read
  from the image file names (e.g. "SE DOMANI NON TORNO.jpg"), skipping opaque ones ("fast1.jpg").
"""

from __future__ import annotations

import asyncio
from datetime import date, datetime, time
from pathlib import PurePosixPath
import re
from urllib.parse import parse_qs, unquote, urljoin, urlparse

from bs4 import BeautifulSoup
import httpx

from app.scrapers.base import BaseScraper, ComingSoonData, ShowtimeData, clean_title

DEFAULT_USER_AGENT = "CNV/0.1.0 (+https://github.com/StardustXYZ/CNVTrue; personal cinema tracker)"
DEFAULT_TIMEOUT = 15.0
DEFAULT_REQUEST_DELAY = 0.5
DEFAULT_CINEMA_NAME = "Cinema Garden"
DEFAULT_BASE_URL = "https://www.cinemagarden.net/default.aspx"


def _normalize_cinema_slug(slug: str) -> str:
    """Return standard cinema name 'Cinema Garden' when given known garden slugs."""
    if slug in ("garden", "cinema-garden", "cinema_garden", "Cinema Garden"):
        return DEFAULT_CINEMA_NAME
    return slug


def extract_available_dates(html: str, base_url: str = DEFAULT_BASE_URL) -> list[tuple[date, str]]:
    """Extract all available calendar dates and their URLs from the schedule page.

    Returns a list of (date_obj, absolute_url) ordered as found on the site.
    """
    soup = BeautifulSoup(html, "html.parser")
    results: list[tuple[date, str]] = []
    seen_dates: set[date] = set()

    # The calendar is typically in .theWeek or via ?data= links
    for a in soup.find_all("a", href=re.compile(r"\?data=\d{1,2}-\d{1,2}-\d{4}", re.IGNORECASE)):
        href = a.get("href", "").strip()
        m = re.search(r"data=(\d{1,2}-\d{1,2}-\d{4})", href, re.IGNORECASE)
        if not m:
            continue
        try:
            d = datetime.strptime(m.group(1), "%d-%m-%Y").date()
        except ValueError:
            continue

        if d not in seen_dates:
            seen_dates.add(d)
            results.append((d, urljoin(base_url, href)))

    return results


def extract_current_page_date(html: str, url: str = "") -> date | None:
    """Determine the date of the showtimes currently displayed in the HTML.

    Inspects URL query parameter first, then the selected day element in .theWeek.
    """
    if url:
        parsed = urlparse(url)
        params = parse_qs(parsed.query)
        if "data" in params and params["data"]:
            try:
                return datetime.strptime(params["data"][0], "%d-%m-%Y").date()
            except ValueError:
                pass

    soup = BeautifulSoup(html, "html.parser")

    # Check for active / selected date indicator in .singleDate
    sel = soup.find(class_=lambda c: c and "singleDate" in c and "selected" in c)
    if sel:
        a_tag = sel.find("a", href=re.compile(r"data=\d{1,2}-\d{1,2}-\d{4}", re.IGNORECASE))
        if a_tag:
            m = re.search(r"data=(\d{1,2}-\d{1,2}-\d{4})", a_tag["href"], re.IGNORECASE)
            if m:
                try:
                    return datetime.strptime(m.group(1), "%d-%m-%Y").date()
                except ValueError:
                    pass

    # Fallback to the first date link found
    first_link = soup.find("a", href=re.compile(r"data=\d{1,2}-\d{1,2}-\d{4}", re.IGNORECASE))
    if first_link:
        m = re.search(r"data=(\d{1,2}-\d{1,2}-\d{4})", first_link["href"], re.IGNORECASE)
        if m:
            try:
                return datetime.strptime(m.group(1), "%d-%m-%Y").date()
            except ValueError:
                pass

    return None


def _purchase_links_after(sala_box) -> dict[str, str]:
    """The film's "Acquista" buttons: one anyticket page per sala ("Sala A", "Sala Garden").

    The times themselves have no link. The buttons come right after the film's times;
    the page's HTML is malformed (film blocks overlap once parsed), so they are read in
    document order, stopping at the next film's times instead of inside the film block.
    """
    links: dict[str, str] = {}
    for el in sala_box.next_elements:
        if getattr(el, "name", None) is None:
            continue
        classes = el.get("class") or []
        if "sala-box" in classes:
            break
        href = (el.get("href") or "").strip()
        if el.name == "a" and "button-acquisto" in classes and href:
            links.setdefault(" ".join(el.stripped_strings).lower(), href)
    return links


def parse_day_showtimes_html(
    html: str,
    cinema_slug: str = DEFAULT_CINEMA_NAME,
    base_url: str = DEFAULT_BASE_URL,
    current_date: date | None = None,
) -> list[ShowtimeData]:
    """Parse showtimes for a single day from Cinema Garden's schedule HTML.

    - Resolves the date from current_date or the page HTML.
    - Accurately captures midnight screenings (00:01).
    - Links to the film details sheet (sala.aspx?p=ID).
    - Ignores the 'Prossimamente' section.
    """
    cinema_name = _normalize_cinema_slug(cinema_slug)
    soup = BeautifulSoup(html, "html.parser")

    if current_date is None:
        current_date = extract_current_page_date(html, base_url) or date.today()

    showtimes: list[ShowtimeData] = []

    # Target specifically the schedule container (.prenota-film) or all .inner-film
    # outside of the .prossimamente-stripe section.
    prenota = soup.find(class_="prenota-film")
    movie_divs = prenota.find_all(class_="inner-film") if prenota else [
        f for f in soup.find_all(class_="inner-film")
        if not f.find_parent(class_="prossimamente-stripe")
    ]

    for m in movie_divs:
        # Title extraction: span[itemprop="name"] or text inside div.titolo
        tit = m.find(class_="titolo")
        if not tit:
            continue

        span = tit.find("span", itemprop="name") or tit.find("span")
        if span:
            raw_title = span.get_text(strip=True)
        else:
            sched = tit.find(class_="schedaFilm")
            sched_text = sched.get_text(strip=True) if sched else ""
            raw_title = tit.get_text(" ", strip=True).replace(sched_text, "").strip()

        if not raw_title:
            continue

        # Movie details sheet URL: sala.aspx?p=ID
        a_sheet = m.find("a", href=lambda h: h and "sala.aspx" in h.lower())
        sheet_href = a_sheet.get("href", "").strip() if a_sheet else ""
        sheet_url = urljoin(base_url, sheet_href) if sheet_href else base_url

        # Parse showtimes in .sala-box -> .unOrario
        sala_box = m.find(class_="sala-box")
        if not sala_box:
            continue

        booking_by_sala = _purchase_links_after(sala_box)

        for uo in sala_box.find_all(class_="unOrario"):
            lines = [s.strip() for s in uo.stripped_strings if s.strip()]
            if not lines:
                continue

            time_val: time | None = None
            sala_val: str | None = None
            extra_tags: list[str] = []

            for line in lines:
                if re.match(r"^\d{1,2}:\d{2}$", line):
                    # Robust parsing for 00:01, 00:00, or standard hours
                    try:
                        time_val = datetime.strptime(line, "%H:%M").time()
                    except ValueError:
                        if line == "24:00":
                            time_val = time(0, 0)
                elif "sala" in line.lower() or any(k in line.lower() for k in ("auditorium", "arena")):
                    if sala_val is None:
                        sala_val = line
                    else:
                        extra_tags.append(line)
                else:
                    extra_tags.append(line)

            if time_val is None:
                continue

            # If sala wasn't recognized by keyword, use any first extra line
            if sala_val is None and extra_tags:
                sala_val = extra_tags.pop(0)

            showtimes.append(
                ShowtimeData(
                    cinema=cinema_name,
                    raw_title=raw_title,
                    date=current_date,
                    time=time_val,
                    sala=sala_val,
                    tags=extra_tags,
                    source_url=sheet_url,
                    booking_url=booking_by_sala.get((sala_val or "").lower(), ""),
                )
            )

    return showtimes


def parse_showtimes_html(
    html: str,
    cinema_slug: str = DEFAULT_CINEMA_NAME,
    base_url: str = DEFAULT_BASE_URL,
    current_date: date | None = None,
) -> list[ShowtimeData]:
    """Compatibility alias for parse_day_showtimes_html."""
    return parse_day_showtimes_html(
        html=html,
        cinema_slug=cinema_slug,
        base_url=base_url,
        current_date=current_date,
    )


def title_from_poster_url(src: str) -> str | None:
    """Turn a poster URL like ".../SE%20DOMANI%20NON%20TORNO.jpg" into a title.

    Returns None for names that are not titles, e.g. "fast1.jpg" or "locandina_03.png".
    """
    stem = PurePosixPath(unquote(urlparse(src).path)).stem
    name = re.sub(r"[_\-]+", " ", stem)
    name = re.sub(r"\s+", " ", name).strip()
    if not re.search(r"[A-Za-zÀ-ÿ]{2}", name):
        return None
    # A single lowercase word glued to a number is a file name, not a title
    if " " not in name and re.search(r"\d$", name):
        return None
    if name.lower().split()[0] in ("locandina", "poster", "banner", "prossimamente", "img", "image", "foto"):
        return None
    return name


def parse_coming_soon_html(html: str, cinema_slug: str = DEFAULT_CINEMA_NAME) -> list[ComingSoonData]:
    """Read the titles of the 'Prossimamente' posters from their file names (no dates available)."""
    soup = BeautifulSoup(html, "html.parser")
    stripe = soup.find(class_="prossimamente-stripe")
    if stripe is None:
        return []
    items: list[ComingSoonData] = []
    seen: set[str] = set()
    for img in stripe.find_all("img"):
        title = title_from_poster_url(img.get("src") or "")
        if title is None or title.lower() in seen:
            continue
        seen.add(title.lower())
        link = img.find_parent("a")
        items.append(
            ComingSoonData(
                cinema=_normalize_cinema_slug(cinema_slug),
                raw_title=title,
                source_url=link.get("href", "") if link else "",
            )
        )
    return items


class CinemaGardenScraper(BaseScraper):
    """Scraper implementation for Cinema Garden (Rende).

    Walks through all available day links (~14 days), parses movie cards and
    handles midnight screenings. If a day page cannot be read the whole scrape fails,
    so a partial programme is never mistaken for cancelled shows.
    """

    def __init__(
        self,
        cinema_slug: str = DEFAULT_CINEMA_NAME,
        url: str = DEFAULT_BASE_URL,
        user_agent: str = DEFAULT_USER_AGENT,
        timeout: float = DEFAULT_TIMEOUT,
        request_delay: float = DEFAULT_REQUEST_DELAY,
    ) -> None:
        normalized_slug = _normalize_cinema_slug(cinema_slug)
        super().__init__(normalized_slug, url)
        self.user_agent = user_agent
        self.timeout = timeout
        self.request_delay = request_delay

    async def scrape(self) -> list[ShowtimeData]:
        """Fetch all available daily schedules for Cinema Garden."""
        headers = {"User-Agent": self.user_agent}
        all_showtimes: list[ShowtimeData] = []

        async with httpx.AsyncClient(headers=headers, timeout=self.timeout, follow_redirects=True) as client:
            resp = await client.get(self.url)
            resp.raise_for_status()
            home_html = resp.text
            final_url = str(resp.url)

            # Discover all dates linked in the calendar
            available_dates = extract_available_dates(home_html, base_url=final_url)
            home_date = extract_current_page_date(home_html, url=final_url)

            # Parse the initial day displayed on the home page
            first_day_shows = parse_day_showtimes_html(
                html=home_html,
                cinema_slug=self.cinema_slug,
                base_url=final_url,
                current_date=home_date,
            )
            all_showtimes.extend(first_day_shows)

            # Fetch remaining available dates
            for d, day_url in available_dates:
                if home_date is not None and d == home_date:
                    continue  # Already parsed above from home page

                await asyncio.sleep(self.request_delay)
                day_resp = await self._get_day(client, day_url)
                day_shows = parse_day_showtimes_html(
                    html=day_resp.text,
                    cinema_slug=self.cinema_slug,
                    base_url=str(day_resp.url),
                    current_date=d,
                )
                all_showtimes.extend(day_shows)

        return all_showtimes

    async def _get_day(self, client: httpx.AsyncClient, url: str) -> httpx.Response:
        """Fetch one day page, retrying once.

        If it keeps failing the error is raised: the sync then treats the whole Garden as
        failed for today, instead of thinking that day's shows were cancelled.
        """
        try:
            resp = await client.get(url)
            resp.raise_for_status()
            return resp
        except httpx.HTTPError:
            await asyncio.sleep(self.request_delay)
            resp = await client.get(url)
            resp.raise_for_status()
            return resp

    async def scrape_coming_soon(self) -> list[ComingSoonData]:
        """Return the films of the 'Prossimamente' banner (titles from poster file names, no dates)."""
        headers = {"User-Agent": self.user_agent}
        async with httpx.AsyncClient(headers=headers, timeout=self.timeout, follow_redirects=True) as client:
            resp = await client.get(self.url)
            resp.raise_for_status()
            return parse_coming_soon_html(resp.text, cinema_slug=self.cinema_slug)


# Convenient alias
GardenScraper = CinemaGardenScraper

