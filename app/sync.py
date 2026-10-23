"""CLI command to execute cinema scrape + database sync and print summary of changes.

Usage:
    python -m app.sync
"""

from __future__ import annotations

import asyncio
from datetime import datetime
import sys

from app.db.engine import SessionLocal, init_db
from app.db.models import Film
from app.services.sync import SyncResult, run_sync


def _setup_stdout_encoding() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass


async def main_async() -> SyncResult:
    _setup_stdout_encoding()
    init_db()

    now = datetime.now()
    print("=" * 80)
    print("CineWatch - Esecuzione Scraping & Sincronizzazione Database")
    print(f"Data sync: {now.strftime('%d/%m/%Y %H:%M:%S')}")
    print("=" * 80)

    with SessionLocal() as db:
        print("\n[>] Connessione e scraping in corso...")
        result = await run_sync(db)

        # 1. Scraper errors if any
        if result.errors:
            print("\n[!] Errori riscontrati durante lo scraping:")
            for slug, err in result.errors.items():
                print(f"  * {slug}: {err}")
        else:
            print("\n[OK] Tutti gli scraper hanno completato con successo.")

        # 2. What changed
        print("\n" + "-" * 80)
        print("RIEPILOGO MODIFICHE")
        print("-" * 80)

        if result.new_films:
            print(f"\n[+] Nuovi film inseriti ({len(result.new_films)}):")
            for f in result.new_films:
                print(f"   * {f.raw_title} (stato: {f.status})")

        status_changes = [c for c in result.status_changes if c.change_type != "new_film"]
        if status_changes:
            print(f"\n[~] Cambiamenti di stato ({len(status_changes)}):")
            for c in status_changes:
                if c.change_type == "reappeared":
                    print(f"   * {c.title}: {c.old_status} -> {c.new_status} (ricomparso, data uscita azzerata)")
                else:
                    print(f"   * {c.title}: {c.old_status} -> {c.new_status} ({c.details})")
        else:
            print("\nNessun cambio di stato per i film esistenti.")

        print(f"\n[OK] Spettacoli elaborati: {result.showtimes}")
        print(f"[OK] Snapshot giornalieri: creati {result.snapshots_created}, aggiornati {result.snapshots_updated}")

        # 3. Overall DB stats
        in_sala_count = db.query(Film).filter_by(status="in_sala").count()
        in_uscita_count = db.query(Film).filter_by(status="in_uscita").count()
        usciti_count = db.query(Film).filter_by(status="uscito").count()

        print("\n" + "=" * 80)
        print(f"STATO ATTUALE DATABASE (Totale film: {result.films})")
        print(f"  * In sala:              {in_sala_count}")
        print(f"  * In uscita (prossimi): {in_uscita_count}")
        print(f"  * Usciti dalle sale:    {usciti_count}")
        print("=" * 80)

        return result


def main() -> None:
    asyncio.run(main_async())


if __name__ == "__main__":
    main()

