"""Scraper for the 18tickets (18Months) cinema ticketing platform.

Supports:
- Andromeda River (Zumpano): https://zumpano.andromeda.andromedacinema.it/
- Cinema Citrigno: https://citrigno.cosenzacinema.18tickets.it/
- Cinema Unical: https://unical.cosenzacinema.18tickets.it/
- Cinema Teatro Italia / Tieri: https://cinemateatroitalia.cosenzacinema.18tickets.it/
"""

from __future__ import annotations

import asyncio
import re
from datetime import date, datetime, time
from urllib.parse import urljoin

from bs4 import BeautifulSoup
import httpx

from app.scrapers.base import BaseScraper, ComingSoonData, ShowtimeData, clean_title

DEFAULT_USER_AGENT = "CNV/0.1.0 (+https://github.com/StardustXYZ/CNVTrue; personal cinema tracker)"
DEFAULT_TIMEOUT = 15.0



def parse_showtimes_html(html: str, cinema_slug: str, base_url: str = "") -> list[ShowtimeData]:
    """Parse showtimes from a 18tickets schedule HTML page.

    Handles multi-day schedules, pre-sales (e.g. December), rooms (sale),
    labels/tags, and film detail URLs.
    """
    soup = BeautifulSoup(html, "html.parser")
    showtimes: list[ShowtimeData] = []

    movie_divs = soup.find_all(class_="movie")
    for m in movie_divs:
        # Extract title & detail sheet URL
        heading = m.find(class_="page-heading")
        title_a = heading.find("a") if heading else m.find("a", class_="movie__title")
        if not title_a:
            continue

        raw_title = title_a.text.strip()
        if not raw_title:
            continue

        href = title_a.get("href", "").strip()
        sheet_url = urljoin(base_url, href) if href else base_url

        # Film-level labels (e.g. 14+, EVENTO 8, #ANTEPRIMA)
        film_labels: list[str] = []
        for el in m.find_all(class_="film-label"):
            txt = el.text.strip()
            if txt and txt not in film_labels:
                film_labels.append(txt)

        # Parse schedule section
        schedule = m.find(class_="schedule-section-show")
        if not schedule:
            continue

        date_places = schedule.find_all(class_="time-select__place")
        for dp in date_places:
            # Parse date DD/MM/YYYY
            date_match = re.search(r"(\d{1,2})/(\d{1,2})/(\d{4})", dp.text)
            if not date_match:
                continue

            try:
                current_date = datetime.strptime(date_match.group(0), "%d/%m/%Y").date()
            except ValueError:
                continue

            # Adjacent column containing showtime buttons
            col_date = dp.find_parent(class_=lambda c: c and "col-" in c)
            col_times = col_date.find_next_sibling(class_=lambda c: c and "col-" in c) if col_date else None
            if not col_times:
                continue

            for a_show in col_times.find_all("a"):
                li = a_show.find("li")
                if not li:
                    continue

                lines = [line.strip() for line in li.stripped_strings if line.strip()]
                if not lines:
                    continue

                time_str = lines[0]
                if not re.match(r"^\d{1,2}:\d{2}$", time_str):
                    continue

                try:
                    show_time = datetime.strptime(time_str, "%H:%M").time()
                except ValueError:
                    continue

                sala_str = lines[1] if len(lines) > 1 else None
                extra_tags = lines[2:] if len(lines) > 2 else []
                # Each time links to the purchase page of that screening
                show_href = (a_show.get("href") or "").strip()
                booking_url = urljoin(base_url, show_href) if "/film/" in show_href else ""

                # Merge film labels and showtime tags, deduplicating while preserving order
                merged_tags: list[str] = []
                for tag in film_labels + extra_tags:
                    if tag and tag not in merged_tags:
                        merged_tags.append(tag)

                showtimes.append(
                    ShowtimeData(
                        cinema=cinema_slug,
                        raw_title=raw_title,
                        date=current_date,
                        time=show_time,
                        sala=sala_str,
                        tags=merged_tags,
                        source_url=sheet_url,
                        booking_url=booking_url,
                    )
                )

    return showtimes


def parse_coming_soon_html(html: str, cinema_slug: str, base_url: str = "") -> list[ComingSoonData]:
    """Parse upcoming films from a 18tickets /coming_soon HTML page."""
    soup = BeautifulSoup(html, "html.parser")
    coming_soon: list[ComingSoonData] = []

    movie_divs = soup.find_all(class_="movie")
    for m in movie_divs:
        heading = m.find(class_="page-heading")
        if not heading:
            continue

        badge = heading.find(class_="badge")
        badge_text = badge.text.strip() if badge else ""
        raw_title = heading.text.replace(badge_text, "").strip()
        if not raw_title:
            continue

        a_tag = m.find("a", href=lambda h: h and "/film/" in h)
        href = a_tag.get("href", "").strip() if a_tag else ""
        sheet_url = urljoin(base_url, href) if href else base_url

        labels: list[str] = []
        for el in m.find_all(class_="film-label"):
            txt = el.text.strip()
            if txt and txt not in labels:
                labels.append(txt)

        rel_date: date | None = None
        date_match = re.search(r"(\d{1,2})/(\d{1,2})/(\d{4})", badge_text)
        if date_match:
            try:
                rel_date = datetime.strptime(date_match.group(0), "%d/%m/%Y").date()
            except ValueError:
                rel_date = None

        coming_soon.append(
            ComingSoonData(
                cinema=cinema_slug,
                raw_title=raw_title,
                release_date=rel_date,
                tags=labels,
                source_url=sheet_url,
            )
        )

    return coming_soon


class EighteenTicketsScraper(BaseScraper):
    """Scraper implementation for 18tickets cinema websites.

    Performs polite HTTP requests with custom User-Agent, timeout, and polite pacing.
    """

    def __init__(
        self,
        cinema_slug: str,
        url: str,
        user_agent: str = DEFAULT_USER_AGENT,
        timeout: float = DEFAULT_TIMEOUT,
    ) -> None:
        super().__init__(cinema_slug, url)
        self.user_agent = user_agent
        self.timeout = timeout

    async def scrape(self) -> list[ShowtimeData]:
        """Fetch the cinema's main schedule page and parse all showtimes."""
        headers = {"User-Agent": self.user_agent}
        async with httpx.AsyncClient(headers=headers, timeout=self.timeout, follow_redirects=True) as client:
            resp = await client.get(self.url)
            resp.raise_for_status()
            return parse_showtimes_html(resp.text, self.cinema_slug, base_url=str(resp.url))

    async def scrape_coming_soon(self) -> list[ComingSoonData]:
        """Fetch the cinema's coming soon page and parse upcoming releases.

        Network and HTTP errors are raised, so the sync can tell a failed page
        (keep the known releases) from a page that is really empty.
        """
        coming_soon_url = urljoin(self.url, "/coming_soon")
        headers = {"User-Agent": self.user_agent}
        async with httpx.AsyncClient(headers=headers, timeout=self.timeout, follow_redirects=True) as client:
            await asyncio.sleep(0.5)  # Polite pause between requests
            resp = await client.get(coming_soon_url)
            resp.raise_for_status()
            return parse_coming_soon_html(resp.text, self.cinema_slug, base_url=str(resp.url))


async def _run_cli_summary() -> None:
    import sys
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass

    from app.config import settings

    target_cinemas = [c for c in settings.CINEMAS if c.scraper in ("18tickets", "eighteen_tickets")]
    if not target_cinemas:
        print("Nessun cinema con scraper 18tickets trovato in config/cinemas.yaml")
        return

    print("=" * 80)
    print("CNV (Chi Ni Vidimu) - Riepilogo scraping 18tickets (Cosenza/Rende)")
    print("=" * 80)

    rows: list[dict[str, str | int]] = []

    for idx, c in enumerate(target_cinemas):
        if idx > 0:
            await asyncio.sleep(1.0)  # Polite delay between cinema sites

        scraper = EighteenTicketsScraper(cinema_slug=c.slug, url=c.url)
        print(f"\n[>] Connessione a {c.name} ({c.url})...")
        try:
            showtimes = await scraper.scrape()
        except Exception as err:
            print(f"[ERR] Errore scraping {c.name}: {err}")
            continue
        # A failing "prossimamente" page does not invalidate the programme read above
        coming_soon_failed = False
        try:
            coming_soon = await scraper.scrape_coming_soon()
        except Exception as err:
            coming_soon, coming_soon_failed = [], True
            print(f"   [!] Prossimamente non disponibile: {err}")

        unique_films = {clean_title(s.raw_title) for s in showtimes}
        dates = [s.date for s in showtimes]
        min_date = min(dates).strftime("%d/%m/%Y") if dates else "-"
        max_date = max(dates).strftime("%d/%m/%Y") if dates else "-"
        date_range = f"{min_date} -> {max_date}" if dates else "-"

        rows.append({
            "name": c.name,
            "slug": c.slug,
            "films": len(unique_films),
            "showtimes": len(showtimes),
            "coming_soon": "ERRORE" if coming_soon_failed else len(coming_soon),
            "date_range": date_range,
        })

        print(f"   [OK] Film in sala: {len(unique_films)}")
        for f in sorted(unique_films):
            f_shows = [s for s in showtimes if clean_title(s.raw_title) == f]
            sample_tags = list({t for s in f_shows for t in s.tags if t})
            tags_str = f" [tags: {', '.join(sample_tags)}]" if sample_tags else ""
            print(f"     * {f} ({len(f_shows)} spettacoli){tags_str}")
        print(f"   [OK] Spettacoli totali: {len(showtimes)} ({date_range})")
        if coming_soon:
            print(f"   [OK] Prossimamente: {len(coming_soon)} titoli")

    print("\n" + "=" * 80)
    print(f"{'CINEMA':<35} | {'FILM':<6} | {'SPETTACOLI':<12} | {'COMING SOON':<12} | {'RANGE DATE'}")
    print("-" * 80)
    for r in rows:
        print(f"{r['name']:<35} | {r['films']:<6} | {r['showtimes']:<12} | {r['coming_soon']:<12} | {r['date_range']}")
    print("=" * 80)


if __name__ == "__main__":
    asyncio.run(_run_cli_summary())

