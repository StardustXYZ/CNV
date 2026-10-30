"""Check that every cinema website answers and can be read (no database, no TMDB).

Used by the GitHub Actions test (.github/workflows/prova-siti.yml) to see whether the
sites answer from GitHub's servers; it also works on this PC.

Usage:
    python -m app.check_sites
Exit code 1 if at least one page could not be read.
"""

from __future__ import annotations

import asyncio
import os
import sys

from app.config import settings
from app.services.sync import SCRAPER_REGISTRY


async def check() -> tuple[list[str], bool]:
    rows = ["| Sito | Pagina | Esito | Dettagli |", "|---|---|---|---|"]
    all_ok = True
    jobs = [(c.name, c.slug, c.scraper, c.url, True) for c in settings.CINEMAS]
    jobs += [(s.name, s.slug, s.scraper, s.url, False) for s in settings.COMING_SOON_SOURCES]

    for name, slug, scraper_name, url, has_programme in jobs:
        scraper = SCRAPER_REGISTRY[scraper_name](cinema_slug=slug, url=url)
        if has_programme:
            try:
                shows = await scraper.scrape()
                days = sorted({s.date for s in shows})
                span = f"{days[0]:%d/%m} → {days[-1]:%d/%m}" if days else "nessun giorno"
                linked = sum(1 for s in shows if s.booking_url)
                rows.append(f"| {name} | programmazione | ✅ | {len(shows)} spettacoli ({span}), {linked} con link d'acquisto |")
            except Exception as err:  # noqa: BLE001 - reported in the table
                all_ok = False
                rows.append(f"| {name} | programmazione | ❌ | {type(err).__name__}: {str(err)[:120]} |")
        await asyncio.sleep(1)
        try:
            coming = await scraper.scrape_coming_soon()
            rows.append(f"| {name} | prossimamente | ✅ | {len(coming)} titoli |")
        except Exception as err:  # noqa: BLE001 - reported in the table
            all_ok = False
            rows.append(f"| {name} | prossimamente | ❌ | {type(err).__name__}: {str(err)[:120]} |")
        await asyncio.sleep(1)
    return rows, all_ok


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    rows, all_ok = asyncio.run(check())
    report = "\n".join(["## Prova dei siti dei cinema", "", *rows, ""])
    print(report)
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:  # shown on the run page on GitHub
        with open(summary, "a", encoding="utf-8") as fh:
            fh.write(report)
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
