"""FastAPI routes for the CineWatch web UI."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.config import settings
from app.db.engine import get_db
from app.db.models import Film
from app.services import export as export_service
from app.services import sync as sync_service
from app.services.tmdb import TmdbClient

router = APIRouter()
templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))


# ------------------------------------------------------------------
# Pages
# ------------------------------------------------------------------


@router.get("/", response_class=HTMLResponse)
def index(request: Request, db: Session = Depends(get_db)):
    """Home page – films currently in theaters."""
    films = (
        db.query(Film)
        .filter(Film.in_theaters == True)  # noqa: E712
        .order_by(Film.raw_title)
        .all()
    )
    return templates.TemplateResponse(request, "index.html", {"films": films})


@router.get("/watchlist", response_class=HTMLResponse)
def watchlist(request: Request, db: Session = Depends(get_db)):
    """Films that left theaters and were marked V or ?."""
    films = (
        db.query(Film)
        .filter(Film.in_theaters == False)  # noqa: E712
        .filter(Film.vote.in_(["V", "?"]))
        .order_by(Film.last_seen.desc())
        .all()
    )
    return templates.TemplateResponse(request, "watchlist.html", {"films": films})


# ------------------------------------------------------------------
# Actions
# ------------------------------------------------------------------


@router.post("/film/{film_id}/vote")
def vote_film(
    film_id: int,
    v: str = Form(...),
    db: Session = Depends(get_db),
):
    """Save a vote (V / ? / X) for a film.  Returns an htmx partial."""
    film = db.get(Film, film_id)
    if film and v in ("V", "?", "X", ""):
        film.vote = v if v else None
        db.commit()
    label = v or "\u2013"
    return HTMLResponse(
        f'<span class="vote-badge vote-{v}">{label}</span>'
    )


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
async def trigger_sync(db: Session = Depends(get_db)):
    """Run all scrapers (plus TMDB matching when a key is set) and redirect to the home page."""
    if settings.TMDB_API_KEY:
        async with TmdbClient() as tmdb:
            await sync_service.run_sync(db, matcher=tmdb)
    else:
        await sync_service.run_sync(db)
    return RedirectResponse(url="/", status_code=303)

