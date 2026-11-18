"""Fix the TMDB match of a film by hand, from the terminal or a small window.

The films come from the database published every night (branch "dati" on GitHub), read
without changing it. A correction is written in config/abbinamenti.yaml: commit and push
that file, and the next nightly sync gives the film its TMDB match (app/services/overrides.py).

Usage:
    python -m app.abbina                    # the window (default)
    python -m app.abbina lista [testo]      # films to check, or films whose title has the text
    python -m app.abbina cerca "titolo"     # search TMDB: id, title, year
    python -m app.abbina imposta FILM TMDB  # film id (from "lista") and TMDB id
    --db percorso.db                        # use a local database instead of downloading it
"""

from __future__ import annotations

import argparse
import asyncio
from datetime import date
from pathlib import Path
import sys
import tempfile

import httpx
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.config import settings
from app.db.models import Film
from app.services.matching import STATUS_NOT_FOUND, STATUS_REVIEW, ScoredCandidate, search_manual
from app.services.overrides import OVERRIDES_PATH, save_override
from app.services.tmdb import TmdbClient

DATABASE_URL = "https://raw.githubusercontent.com/StardustXYZ/CNV/dati/cnv.db"
REVIEW_STATUSES = (STATUS_REVIEW, STATUS_NOT_FOUND)
MAX_CANDIDATES = 8


def fetch_database(dest: Path | None = None) -> Path:
    """Download the nightly database (public) into a temporary file."""
    dest = dest or Path(tempfile.gettempdir()) / "cnv-dati.db"
    resp = httpx.get(DATABASE_URL, follow_redirects=True, timeout=30)
    resp.raise_for_status()
    dest.write_bytes(resp.content)
    return dest


def open_database(path: Path) -> Session:
    return Session(create_engine(f"sqlite:///{path.as_posix()}"))


def films_to_review(db: Session) -> list[Film]:
    return (
        db.query(Film)
        .filter(Film.tmdb_match_status.in_(REVIEW_STATUSES))
        .order_by(Film.tmdb_match_status, Film.raw_title)
        .all()
    )


def find_films(db: Session, text: str) -> list[Film]:
    like = f"%{text.strip().lower()}%"
    return (
        db.query(Film)
        .filter(Film.raw_title.ilike(like) | Film.tmdb_title.ilike(like))
        .order_by(Film.raw_title)
        .all()
    )


def describe(film: Film) -> str:
    """One line: id, title as the cinemas write it, and what TMDB says about it now."""
    if film.tmdb_id is None:
        match = "nessun abbinamento"
    else:
        label = "suggerito" if film.tmdb_match_status in REVIEW_STATUSES else "abbinato"
        match = f"{label}: {film.tmdb_title or '?'} ({film.year or '?'}) [TMDB {film.tmdb_id}]"
    return f"{film.id:>5}  {film.raw_title}  ->  {match}"


async def search(query: str) -> list[ScoredCandidate]:
    if not settings.TMDB_API_KEY:
        raise RuntimeError("Manca TMDB_API_KEY nel file .env")
    async with TmdbClient() as tmdb:
        return (await search_manual(tmdb, query, date.today()))[:MAX_CANDIDATES]


def describe_candidate(c: ScoredCandidate) -> str:
    m = c.movie
    original = f" - {m.original_title}" if m.original_title and m.original_title != m.title else ""
    return f"{m.id:>8}  {m.title}{original} ({m.year or '?'})"


def choose(db: Session, film_id: int, tmdb_id: int, path: Path = OVERRIDES_PATH) -> Film:
    """Write the correction for a film of the database in the file of the matches."""
    film = db.get(Film, film_id)
    if film is None:
        raise ValueError(f"Nel database non c'è nessun film con id {film_id}")
    save_override(film.normalized_title, tmdb_id, path)
    return film


def _database(args: argparse.Namespace) -> Session:
    path = Path(args.db) if args.db else fetch_database()
    return open_database(path)


def _saved_message(film: Film, tmdb_id: int) -> str:
    return (
        f"Salvato: {film.raw_title} -> TMDB {tmdb_id} (config/abbinamenti.yaml).\n"
        "Per renderlo valido fai commit e push di quel file: lo applica il prossimo aggiornamento notturno."
    )


def run_cli(args: argparse.Namespace) -> int:
    if args.command == "cerca":
        try:
            found = asyncio.run(search(args.testo))
        except (RuntimeError, httpx.HTTPError) as err:
            print(f"Ricerca non riuscita: {err}")
            return 1
        print("\n".join(describe_candidate(c) for c in found) or "Nessun risultato")
        return 0

    with _database(args) as db:
        if args.command == "lista":
            films = find_films(db, args.testo) if args.testo else films_to_review(db)
            print("\n".join(describe(f) for f in films) or "Nessun film da verificare")
            return 0
        try:
            film = choose(db, args.film, args.tmdb)
        except ValueError as err:
            print(err)
            return 1
        print(_saved_message(film, args.tmdb))
        return 0


def run_window(args: argparse.Namespace) -> int:
    import tkinter as tk
    from tkinter import messagebox, ttk

    try:
        db = _database(args)
    except httpx.HTTPError as err:
        print(f"Non riesco a scaricare il database: {err}")
        return 1

    root = tk.Tk()
    root.title("CNV - abbinamenti TMDB")
    root.geometry("980x520")
    films: list[Film] = []
    candidates: list[ScoredCandidate] = []

    left, right = ttk.Frame(root, padding=8), ttk.Frame(root, padding=8)
    left.pack(side="left", fill="both", expand=True)
    right.pack(side="right", fill="both", expand=True)

    ttk.Label(left, text="Film (da verificare, o cerca per titolo)").pack(anchor="w")
    find_var = tk.StringVar()
    find_entry = ttk.Entry(left, textvariable=find_var)
    find_entry.pack(fill="x")
    film_list = tk.Listbox(left, exportselection=False)
    film_list.pack(fill="both", expand=True, pady=4)
    suggestion = ttk.Label(left, text="", wraplength=440)
    suggestion.pack(anchor="w")
    use_suggestion = ttk.Button(left, text="Conferma il suggerimento")
    use_suggestion.pack(anchor="w", pady=4)

    ttk.Label(right, text="Cerca su TMDB").pack(anchor="w")
    query_var = tk.StringVar()
    query_entry = ttk.Entry(right, textvariable=query_var)
    query_entry.pack(fill="x")
    result_list = tk.Listbox(right, exportselection=False)
    result_list.pack(fill="both", expand=True, pady=4)
    use_result = ttk.Button(right, text="Usa il film selezionato")
    use_result.pack(anchor="w", pady=4)
    status = ttk.Label(root, text="", wraplength=940)
    status.pack(side="bottom", fill="x", padx=8, pady=4)

    def current_film() -> Film | None:
        picked = film_list.curselection()
        return films[picked[0]] if picked else None

    def load_films(*_):
        nonlocal films
        text = find_var.get().strip()
        films = find_films(db, text) if text else films_to_review(db)
        film_list.delete(0, "end")
        for f in films:
            film_list.insert("end", describe(f))
        if not films:
            status.config(text="Nessun film da verificare" if not text else "Nessun film con questo titolo")

    def film_picked(*_):
        film = current_film()
        if film is None:
            return
        suggestion.config(
            text=f"Suggerito da CNV: {film.tmdb_title} ({film.year or '?'})" if film.tmdb_id else "Nessun suggerimento"
        )
        query_var.set(film.raw_title)
        run_search()

    def run_search(*_):
        nonlocal candidates
        result_list.delete(0, "end")
        try:
            candidates = asyncio.run(search(query_var.get()))
        except (RuntimeError, httpx.HTTPError) as err:
            candidates = []
            status.config(text=f"Ricerca non riuscita: {err}")
            return
        for c in candidates:
            result_list.insert("end", describe_candidate(c))
        status.config(text="" if candidates else "Nessun risultato")

    def save(film: Film | None, tmdb_id: int | None):
        if film is None or tmdb_id is None:
            messagebox.showinfo("CNV", "Scegli prima un film e un abbinamento.")
            return
        choose(db, film.id, tmdb_id)
        status.config(text=_saved_message(film, tmdb_id))

    def save_suggestion():
        film = current_film()
        save(film, film.tmdb_id if film else None)

    def save_result():
        picked = result_list.curselection()
        save(current_film(), candidates[picked[0]].movie.id if picked else None)

    find_entry.bind("<Return>", load_films)
    query_entry.bind("<Return>", run_search)
    film_list.bind("<<ListboxSelect>>", film_picked)
    use_suggestion.config(command=save_suggestion)
    use_result.config(command=save_result)
    load_films()
    root.mainloop()
    db.close()
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Abbinamenti dei film a TMDB, a mano")
    parser.add_argument("--db", help="database locale da usare invece di scaricare quello notturno")
    commands = parser.add_subparsers(dest="command")
    commands.add_parser("finestra", help="la finestra (predefinito)")
    lista = commands.add_parser("lista", help="film da verificare, o con il testo nel titolo")
    lista.add_argument("testo", nargs="?", default="")
    cerca = commands.add_parser("cerca", help="cerca un titolo su TMDB")
    cerca.add_argument("testo")
    imposta = commands.add_parser("imposta", help="abbina il film (id di 'lista') al film TMDB")
    imposta.add_argument("film", type=int)
    imposta.add_argument("tmdb", type=int)
    args = parser.parse_args(argv)
    if args.command in (None, "finestra"):
        return run_window(args)
    return run_cli(args)


if __name__ == "__main__":
    sys.exit(main())
