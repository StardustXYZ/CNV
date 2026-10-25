"""CLI command to execute cinema scrape + database sync and print summary of changes.

Usage:
    python -m app.sync
"""

from __future__ import annotations

import asyncio
from datetime import datetime
import sys

from app.config import settings
from app.db.engine import SessionLocal, init_db
from app.db.models import Film
from app.logging_setup import configure_logging
from app.services.matching import MatchReport
from app.services.runner import SyncAlreadyRunning, run_full_sync
from app.services.sync import SyncResult


def _setup_stdout_encoding() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass


async def main_async() -> SyncResult:
    _setup_stdout_encoding()
    configure_logging()
    init_db()

    now = datetime.now()
    print("=" * 80)
    print("CNV (Chi Ni Vidimu) - Esecuzione Scraping & Sincronizzazione Database")
    print(f"Data sync: {now.strftime('%d/%m/%Y %H:%M:%S')}")
    print("=" * 80)

    with SessionLocal() as db:
        print("\n[>] Connessione e scraping in corso...")
        if not settings.TMDB_API_KEY:
            print("[!] TMDB_API_KEY non configurata: matching TMDB saltato.")
        try:
            result, log = await run_full_sync(db, "terminale")
        except SyncAlreadyRunning:
            print("\n[!] C'è già un sync in corso (dall'app web o da un altro terminale). Riprova tra poco.")
            sys.exit(1)
        if log.backup_file:
            print(f"[OK] Backup del database: backups/{log.backup_file}")

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

        if result.coming_soon:
            print("\n[>] Film annunciati (prossimamente) per fonte:")
            for source, count in result.coming_soon.items():
                print(f"   * {source}: {count}")

        if result.matching is not None:
            _print_matching(result.matching)

        print(f"\n[OK] Spettacoli elaborati: {result.showtimes}")
        if result.showtimes_removed:
            print(f"[~] Spettacoli tolti perché cancellati o spostati dai cinema: {result.showtimes_removed}")
        print(f"[OK] Snapshot giornalieri: creati {result.snapshots_created}, aggiornati {result.snapshots_updated}")

        # 3. Overall DB stats
        in_sala_count = db.query(Film).filter_by(status="in_sala").count()
        in_uscita_count = db.query(Film).filter_by(status="in_uscita").count()
        usciti_count = db.query(Film).filter_by(status="uscito").count()
        review_count = db.query(Film).filter(Film.tmdb_match_status.in_(("da_verificare", "non_trovato"))).count()

        print("\n" + "=" * 80)
        print(f"STATO ATTUALE DATABASE (Totale film: {result.films})")
        print(f"  * In sala:              {in_sala_count}")
        print(f"  * In uscita (prossimi): {in_uscita_count}")
        print(f"  * Usciti dalle sale:    {usciti_count}")
        print(f"  * TMDB da verificare:   {review_count}")
        print("=" * 80)

        return result


def _print_matching(report: MatchReport) -> None:
    print("\n" + "-" * 80)
    print("MATCHING TMDB")
    print("-" * 80)
    if report.matched:
        print(f"\n[OK] Abbinati ({len(report.matched)}):")
        for f in report.matched:
            print(f"   * {f.raw_title} -> {f.tmdb_title} ({f.year or '?'}) [TMDB {f.tmdb_id}, {f.tmdb_confidence:.2f}]")
    if report.merged_titles:
        print(f"\n[=] Doppioni uniti ({len(report.merged_titles)}):")
        for merged, survivor in report.merged_titles:
            print(f"   * {merged} -> {survivor}")
    if report.to_review:
        print(f"\n[?] Da verificare ({len(report.to_review)}):")
        for f in report.to_review:
            print(f"   * {f.raw_title} -> forse {f.tmdb_title} ({f.year or '?'}) [{f.tmdb_confidence:.2f}]")
    if report.not_found:
        print(f"\n[x] Non trovati su TMDB ({len(report.not_found)}):")
        for f in report.not_found:
            print(f"   * {f.raw_title}")
    if report.errors:
        print("\n[!] Errori TMDB:")
        for err in report.errors:
            print(f"   * {err}")
    if not (report.matched or report.to_review or report.not_found or report.errors):
        print("\nNessun film nuovo da abbinare.")


def main() -> None:
    asyncio.run(main_async())


if __name__ == "__main__":
    main()

