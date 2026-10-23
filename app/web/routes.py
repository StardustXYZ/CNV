"""FastAPI routes for the CineWatch web UI."""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from datetime import date, time, timedelta
from pathlib import Path
from urllib.parse import urlsplit

import httpx
from fastapi import APIRouter, Depends, Form, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response, StreamingResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.config import settings
from app.db.engine import get_db
from app.db.models import Cinema, Film, Showtime
from app.services import export as export_service
from app.services import sync as sync_service
from app.services.matching import STATUS_NOT_FOUND, STATUS_REVIEW, confirm_match, search_manual
from app.services.tmdb import TmdbClient

router = APIRouter()
templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))
STATIC_DIR = Path(__file__).parent / "static"

WEEKDAYS = ["lun", "mar", "mer", "gio", "ven", "sab", "dom"]
MONTHS = [
    "gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno",
    "luglio", "agosto", "settembre", "ottobre", "novembre", "dicembre",
]
VOTES = ("V", "?", "X")
VOTE_FILTERS = {"V": "V", "?": "?", "X": "X", "nessuno": None}
REVIEW_STATUSES = (STATUS_REVIEW, STATUS_NOT_FOUND)
DAYS_PER_CINEMA = 3


def format_day(d: date, today: date | None = None) -> str:
    """'oggi', 'domani' or e.g. 'ven 24/10'."""
    today = today or date.today()
    if d == today:
        return "oggi"
    if d == today + timedelta(days=1):
        return "domani"
    return f"{WEEKDAYS[d.weekday()]} {d.day}/{d.month}"


def format_long_date(d: date, today: date | None = None) -> str:
    """e.g. '16 dicembre', with the year only when it is not the current one."""
    today = today or date.today()
    text = f"{d.day} {MONTHS[d.month - 1]}"
    return text if d.year == today.year else f"{text} {d.year}"


def asset_version(name: str) -> int:
    """Cache-busting value for a static file: changes whenever the file is edited."""
    return int((STATIC_DIR / name).stat().st_mtime)


templates.env.filters["giorno"] = format_day
templates.env.filters["data_lunga"] = format_long_date
templates.env.globals["asset_version"] = asset_version


async def get_tmdb() -> AsyncIterator[TmdbClient | None]:
    """FastAPI dependency – a TMDB client, or None when no API key is configured."""
    if not settings.TMDB_API_KEY:
        yield None
        return
    async with TmdbClient() as client:
        yield client


# ------------------------------------------------------------------
# View models
# ------------------------------------------------------------------


@dataclass
class CinemaSchedule:
    cinema: str
    days: list[tuple[date, list[time]]] = field(default_factory=list)
    more_days: int = 0  # further days not shown


@dataclass
class FilmCard:
    film: Film
    schedule: list[CinemaSchedule] = field(default_factory=list)
    first_date: date | None = None  # first upcoming screening

    @property
    def title(self) -> str:
        return self.film.tmdb_title if self.film.is_tmdb_confirmed and self.film.tmdb_title else self.film.raw_title


def _film_cards(db: Session, films: list[Film], today: date) -> list[FilmCard]:
    """Attach the upcoming screenings (grouped by cinema and day) to each film."""
    cards = {f.id: FilmCard(film=f) for f in films}
    if not cards:
        return []
    rows = (
        db.query(Showtime.film_id, Cinema.name, Showtime.date, Showtime.time)
        .join(Cinema, Cinema.id == Showtime.cinema_id)
        .filter(Showtime.film_id.in_(cards), Showtime.date >= today)
        .order_by(Showtime.date, Showtime.time)
        .all()
    )
    grouped: dict[int, dict[str, dict[date, list[time]]]] = {}
    for film_id, cinema_name, day, at in rows:
        times = grouped.setdefault(film_id, {}).setdefault(cinema_name, {}).setdefault(day, [])
        if at not in times:
            times.append(at)

    for film_id, by_cinema in grouped.items():
        card = cards[film_id]
        for cinema_name, by_day in by_cinema.items():
            days = list(by_day.items())
            card.schedule.append(
                CinemaSchedule(
                    cinema=cinema_name,
                    days=days[:DAYS_PER_CINEMA],
                    more_days=max(0, len(days) - DAYS_PER_CINEMA),
                )
            )
            if card.first_date is None or days[0][0] < card.first_date:
                card.first_date = days[0][0]
        card.schedule.sort(key=lambda s: (s.days[0][0], s.cinema))
    return list(cards.values())


def _nav_counts(db: Session) -> dict[str, int]:
    return {
        "in_sala": db.query(Film).filter_by(status="in_sala").count(),
        "in_uscita": db.query(Film).filter_by(status="in_uscita").count(),
        "da_verificare": db.query(Film).filter(Film.tmdb_match_status.in_(REVIEW_STATUSES)).count(),
        "watchlist": db.query(Film).filter(Film.status == "uscito", Film.vote.in_(["V", "?"])).count(),
    }


def _render(request: Request, db: Session, name: str, active: str, **context) -> HTMLResponse:
    context.update(active=active, counts=_nav_counts(db), today=date.today(), votes=VOTES)
    return templates.TemplateResponse(request, name, context)


def _get_film(db: Session, film_id: int) -> Film:
    film = db.get(Film, film_id)
    if film is None:
        raise HTTPException(status_code=404, detail="Film non trovato")
    return film


def _is_htmx(request: Request) -> bool:
    return request.headers.get("HX-Request") == "true"


# ------------------------------------------------------------------
# Pages
# ------------------------------------------------------------------


@router.get("/", response_class=HTMLResponse)
def index(request: Request, voto: str | None = Query(None), db: Session = Depends(get_db)):
    """Home page – films currently in theaters, optionally filtered by vote."""
    query = db.query(Film).filter_by(status="in_sala")
    if voto in VOTE_FILTERS:
        query = query.filter(Film.vote.is_(None) if voto == "nessuno" else Film.vote == VOTE_FILTERS[voto])
    else:
        voto = None
    cards = sorted(_film_cards(db, query.all(), date.today()), key=lambda c: c.title.lower())
    return _render(request, db, "index.html", "in_sala", cards=cards, voto=voto)


@router.get("/in-uscita", response_class=HTMLResponse)
def coming_soon(request: Request, db: Session = Depends(get_db)):
    """Films whose screenings are all in the future, soonest first."""
    films = db.query(Film).filter_by(status="in_uscita").all()
    cards = sorted(
        _film_cards(db, films, date.today()),
        key=lambda c: (c.first_date is None, c.first_date or date.max, c.title.lower()),
    )
    return _render(request, db, "in_uscita.html", "in_uscita", cards=cards)


@router.get("/da-verificare", response_class=HTMLResponse)
def review(request: Request, db: Session = Depends(get_db)):
    """Films whose TMDB match is uncertain or missing."""
    films = (
        db.query(Film)
        .filter(Film.tmdb_match_status.in_(REVIEW_STATUSES))
        .order_by(Film.tmdb_match_status, Film.raw_title)
        .all()
    )
    cards = _film_cards(db, films, date.today())
    return _render(request, db, "da_verificare.html", "da_verificare", cards=cards, tmdb_enabled=bool(settings.TMDB_API_KEY))


@router.get("/watchlist", response_class=HTMLResponse)
def watchlist(request: Request, db: Session = Depends(get_db)):
    """Films that left theaters and were marked V or ?."""
    films = (
        db.query(Film)
        .filter(Film.status == "uscito", Film.vote.in_(["V", "?"]))
        .order_by(Film.left_theaters_date.desc(), Film.raw_title)
        .all()
    )
    cards = [FilmCard(film=f) for f in films]
    return _render(request, db, "watchlist.html", "watchlist", cards=cards)


# ------------------------------------------------------------------
# Actions
# ------------------------------------------------------------------


@router.post("/film/{film_id}/vote", response_class=HTMLResponse)
def vote_film(request: Request, film_id: int, v: str = Form(""), db: Session = Depends(get_db)):
    """Save a vote (V / ? / X). Clicking the current vote again removes it. Returns an htmx partial."""
    film = _get_film(db, film_id)
    if v not in (*VOTES, ""):
        raise HTTPException(status_code=422, detail="Voto non valido")
    film.vote = None if v in ("", film.vote) else v
    db.commit()
    return templates.TemplateResponse(request, "_vote.html", {"film": film, "votes": VOTES})


@router.post("/film/{film_id}/tmdb/conferma")
def confirm_suggestion(request: Request, film_id: int, db: Session = Depends(get_db)):
    """Confirm the TMDB suggestion of a film to review."""
    film = _get_film(db, film_id)
    try:
        confirm_match(db, film)
    except ValueError as err:
        raise HTTPException(status_code=400, detail=str(err)) from err
    db.commit()
    return Response(status_code=200) if _is_htmx(request) else RedirectResponse("/da-verificare", status_code=303)


@router.get("/film/{film_id}/tmdb/cerca", response_class=HTMLResponse)
async def search_tmdb(
    request: Request,
    film_id: int,
    q: str = Query(""),
    db: Session = Depends(get_db),
    tmdb: TmdbClient | None = Depends(get_tmdb),
):
    """Search TMDB with the user's query and return candidates as an htmx partial."""
    film = _get_film(db, film_id)
    context: dict = {"film": film, "candidates": [], "error": None, "query": q.strip()}
    if tmdb is None:
        context["error"] = "Chiave TMDB non configurata."
    elif context["query"]:
        try:
            context["candidates"] = (await search_manual(tmdb, context["query"], date.today()))[:8]
        except httpx.HTTPError:
            context["error"] = "TMDB non risponde, riprova tra poco."
    return templates.TemplateResponse(request, "_candidates.html", context)


@router.post("/film/{film_id}/tmdb/scegli")
async def choose_candidate(
    request: Request,
    film_id: int,
    tmdb_id: int = Form(...),
    db: Session = Depends(get_db),
    tmdb: TmdbClient | None = Depends(get_tmdb),
):
    """Assign the TMDB film picked by the user, merging duplicates."""
    film = _get_film(db, film_id)
    if tmdb is None:
        raise HTTPException(status_code=503, detail="Chiave TMDB non configurata")
    try:
        movie = await tmdb.get_movie(tmdb_id)
    except httpx.HTTPError as err:
        raise HTTPException(status_code=502, detail="TMDB non risponde") from err
    if movie is None:
        raise HTTPException(status_code=404, detail="Film TMDB non trovato")
    confirm_match(db, film, movie)
    db.commit()
    return Response(status_code=200) if _is_htmx(request) else RedirectResponse("/da-verificare", status_code=303)


@router.get("/export")
def export_csv(db: Session = Depends(get_db)):
    """Download a Letterboxd-compatible CSV watchlist."""
    csv_content = export_service.export_letterboxd_csv(db)
    return StreamingResponse(
        iter([csv_content]),
        media_type="text/csv",
        headers={
            "Content-Disposition": "attachment; filename=letterboxd_watchlist.csv"
        },
    )


@router.post("/sync")
async def trigger_sync(
    request: Request,
    db: Session = Depends(get_db),
    tmdb: TmdbClient | None = Depends(get_tmdb),
):
    """Run all scrapers (plus TMDB matching when a key is set) and go back to the previous page."""
    await sync_service.run_sync(db, matcher=tmdb)
    # Only the path of the referring page, so the redirect never leaves the app
    back = urlsplit(request.headers.get("referer") or "").path or "/"
    return RedirectResponse(url=back, status_code=303)
