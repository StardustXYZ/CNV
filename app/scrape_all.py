"""Unified CLI command to run all cinema scrapers and print summary.

Usage:
    python -m app.scrape_all
"""

from __future__ import annotations

import asyncio
import sys
from datetime import date

from app.config import CinemaConfig, settings
from app.scrapers.base import ShowtimeData, clean_title
from app.services.sync import SCRAPER_REGISTRY


def _setup_stdout_encoding() -> None:
    """Ensure standard output handles UTF-8 characters on all platforms."""
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass


async def scrape_all(
    cinemas: list[CinemaConfig] | None = None,
    delay_between_cinemas: float = 1.0,
) -> list[dict[str, str | int]]:
    """Run all configured scrapers and return summary statistics.

    Args:
        cinemas: Optional list of cinemas to scrape. Defaults to settings.CINEMAS.
        delay_between_cinemas: Seconds to pause between different cinema hosts.

    Returns:
        List of dicts containing summary row for each scraped cinema.
    """
    _setup_stdout_encoding()

    target_cinemas = cinemas if cinemas is not None else settings.CINEMAS
    if not target_cinemas:
        print("Nessun cinema configurato in config/cinemas.yaml")
        return []

    print("=" * 80)
    print("CineWatch - Riepilogo scraping cinema (Cosenza/Rende)")
    print("=" * 80)

    rows: list[dict[str, str | int]] = []
    total_showtimes_all = 0
    total_films_all: set[str] = set()

    for idx, c in enumerate(target_cinemas):
        scraper_cls = SCRAPER_REGISTRY.get(c.scraper)
        if scraper_cls is None:
            print(f"\n[SKIP] Nessuno scraper registrato per '{c.name}' (scraper={c.scraper})")
            continue

        if idx > 0 and delay_between_cinemas > 0:
            await asyncio.sleep(delay_between_cinemas)

        scraper = scraper_cls(cinema_slug=c.slug, url=c.url)
        print(f"\n[>] Connessione a {c.name} ({c.url})...")

        try:
            showtimes = await scraper.scrape()
            coming_soon = await scraper.scrape_coming_soon()
        except Exception as err:
            print(f"[ERR] Errore scraping {c.name}: {err}")
            rows.append({
                "name": c.name,
                "slug": c.slug,
                "films": 0,
                "showtimes": 0,
                "coming_soon": 0,
                "date_range": "ERRORE",
            })
            continue

        unique_films = {clean_title(s.raw_title) for s in showtimes if s.raw_title}
        total_films_all.update(unique_films)
        total_showtimes_all += len(showtimes)

        dates = [s.date for s in showtimes]
        min_date = min(dates).strftime("%d/%m/%Y") if dates else "-"
        max_date = max(dates).strftime("%d/%m/%Y") if dates else "-"
        date_range = f"{min_date} -> {max_date}" if dates else "-"

        rows.append({
            "name": c.name,
            "slug": c.slug,
            "films": len(unique_films),
            "showtimes": len(showtimes),
            "coming_soon": len(coming_soon),
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

    # Summary table
    print("\n" + "=" * 80)
    print(f"{'CINEMA':<35} | {'FILM':<6} | {'SPETTACOLI':<12} | {'COMING SOON':<12} | {'RANGE DATE'}")
    print("-" * 80)
    for r in rows:
        print(f"{r['name']:<35} | {r['films']:<6} | {r['showtimes']:<12} | {r['coming_soon']:<12} | {r['date_range']}")
    print("-" * 80)
    print(f"{'TOTALE: ' + str(len(rows)) + ' cinema':<35} | {len(total_films_all):<6} | {total_showtimes_all:<12} | {'':<12} |")
    print("=" * 80)

    return rows


def main() -> None:
    asyncio.run(scrape_all())


if __name__ == "__main__":
    main()

