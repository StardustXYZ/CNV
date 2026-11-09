"""FastAPI routes for the CNV (Chi Ni Vidimu) web UI."""

from __future__ import annotations

import calendar
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlencode, urlsplit

import httpx
from fastapi import APIRouter, Depends, Form, HTTPException, Query, Request
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse, Response, StreamingResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.config import settings
from app.db.engine import get_db
from app.db.models import Cinema, ComingSoon, Film, Showtime, SyncLog, SyncRun
from app.logging_setup import LOG_FILE_NAME
from app.services import export as export_service
from app.services.backup import list_backups
from app.services.matching import STATUS_NOT_FOUND, STATUS_REVIEW, confirm_match, search_manual
from app.services.runner import SyncAlreadyRunning, is_sync_running, run_full_sync
from app.services.schedule import programme_day, show_datetime, show_end
from app.services.sync import cinemas_not_updated, is_event_film
from app.services.titles import normalize_title
from app.services.tmdb import TmdbClient

router = APIRouter()
templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))
STATIC_DIR = Path(__file__).parent / "static"

WEEKDAYS = ["lun", "mar", "mer", "gio", "ven", "sab", "dom"]
MONTHS = [
    "gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno",
    "luglio", "agosto", "settembre", "ottobre", "novembre", "dicembre",
]
VOTES = ("V", "?", "S")  # V: voglio vederlo, ?: indeciso, S: visto (shown as ✓)
VOTE_LABELS = {"V": "V", "?": "?", "S": "✓"}
VOTE_TITLES = {"V": "Voglio vederlo", "?": "Indeciso", "S": "Visto"}
VOTE_FILTERS = {"V": "V", "?": "?", "nessuno": None}
REVIEW_STATUSES = (STATUS_REVIEW, STATUS_NOT_FOUND)


def _now() -> datetime:
    """Current local time (a function so tests can freeze it)."""
    return datetime.now()


def format_day(d: date, today: date | None = None) -> str:
    """'oggi', 'domani' or e.g. 'ven 24/10'."""
    today = today or date.today()
    if d == today:
        return "oggi"
    if d == today + timedelta(days=1):
        return "domani"
    return f"{WEEKDAYS[d.weekday()]} {d.day}/{d.month}"


def format_runtime(minutes: int) -> str:
    """e.g. '1h 55m', '2h', '45m'."""
    hours, rest = divmod(minutes, 60)
    if not hours:
        return f"{rest}m"
    return f"{hours}h {rest:02d}m" if rest else f"{hours}h"


def format_long_date(d: date, today: date | None = None) -> str:
    """e.g. '16 dicembre', with the year only when it is not the current one."""
    today = today or date.today()
    text = f"{d.day} {MONTHS[d.month - 1]}"
    return text if d.year == today.year else f"{text} {d.year}"


def format_local_time(value: datetime | None) -> str:
    """UTC timestamp from the database shown in local time, e.g. '23/10 21:23'."""
    if value is None:
        return "–"
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone().strftime("%d/%m %H:%M")


def asset_version(name: str) -> int:
    """Cache-busting value for a static file: changes whenever the file is edited."""
    return int((STATIC_DIR / name).stat().st_mtime)


templates.env.filters["giorno"] = format_day
templates.env.filters["data_lunga"] = format_long_date
templates.env.filters["durata"] = format_runtime
templates.env.globals["WEEKDAYS"] = WEEKDAYS
templates.env.globals["VOTE_LABELS"] = VOTE_LABELS
templates.env.globals["VOTE_TITLES"] = VOTE_TITLES
templates.env.globals["asset_version"] = asset_version
templates.env.filters["ora_locale"] = format_local_time


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
class ShowLink:
    start: datetime
    url: str  # where to buy it: the screening's page, else the film's page on the cinema site
    end: datetime | None = None  # estimated from the TMDB runtime


@dataclass
class SalaShows:
    sala: str | None
    shows: list[ShowLink] = field(default_factory=list)

    @property
    def first_start(self) -> datetime:
        return self.shows[0].start


@dataclass
class CinemaToday:
    cinema: str
    slug: str
    salas: list[SalaShows] = field(default_factory=list)


def _group_by_sala(by_sala: dict[str | None, dict[datetime, str]], film: Film | None = None) -> list[SalaShows]:
    """{sala: {start: url}} -> salas sorted by their first show, shows sorted by time.

    With the ``film`` and its TMDB runtime each show also gets its estimated end.
    """
    runtime = film.runtime if film is not None and film.has_tmdb_details else None
    salas = [
        SalaShows(
            sala=sala,
            shows=[ShowLink(start=start, url=url, end=show_end(start, runtime)) for start, url in sorted(starts.items())],
        )
        for sala, starts in by_sala.items()
    ]
    return sorted(salas, key=lambda s: (s.first_start, s.sala or ""))


def _show_url(booking_url: str | None, source_url: str | None, cinema_url: str) -> str:
    return booking_url or source_url or cinema_url


@dataclass
class CinemaRelease:
    cinema: str
    first_date: date | None  # None: announced without a date
    announced: bool = False  # only in a coming-soon list, no showtimes yet


@dataclass
class FilmCard:
    film: Film
    # Next shows: the rest of today, or when today is over the next day with shows
    next_shows: list[CinemaToday] = field(default_factory=list)
    next_day: date | None = None  # day of next_shows
    next_is_today: bool = False  # next_shows are today's (programme day), not a later day
    cinemas: list[CinemaRelease] = field(default_factory=list)  # cinemas with upcoming shows or announcements
    first_date: date | None = None  # first known date anywhere
    has_shows: bool = False  # has screenings that have not started yet
    exit_date: date | None = None  # when a film no longer programmed becomes "uscito"
    in_sala_since: date | None = None  # first day it was screened in a cinema of the area

    @property
    def title(self) -> str:
        return self.film.tmdb_title if self.film.is_tmdb_confirmed and self.film.tmdb_title else self.film.raw_title

    @property
    def announced_elsewhere(self) -> list[CinemaRelease]:
        """Cinemas that announce the film without programming it yet."""
        return [c for c in self.cinemas if c.announced]


def _film_cards(db: Session, films: list[Film], now: datetime, cinema_slug: str | None = None) -> list[FilmCard]:
    """Attach to each film its next shows (by cinema and sala) and its cinemas.

    The next shows are the ones still to come today; when today is over (or the film
    is not on today) they are the ones of the next day with shows. With ``cinema_slug``
    only that cinema counts.
    """
    cards = {f.id: FilmCard(film=f) for f in films}
    if not cards:
        return []
    day = programme_day(now)
    rows = (
        db.query(
            Showtime.film_id, Cinema.name, Cinema.slug, Cinema.url, Showtime.sala, Showtime.date, Showtime.time,
            Showtime.booking_url, Showtime.source_url,
        )
        .join(Cinema, Cinema.id == Showtime.cinema_id)
        .filter(Showtime.film_id.in_(cards), Showtime.date >= day)
        .filter(Cinema.slug == cinema_slug if cinema_slug else True)
        .all()
    )

    # film -> day -> (cinema, slug) -> sala -> {start: url}, only shows not started yet
    upcoming: dict[int, dict[date, dict[tuple[str, str], dict[str | None, dict[datetime, str]]]]] = {}
    first_by_cinema: dict[int, dict[str, date]] = {}
    for film_id, cinema_name, slug, cinema_url, sala, show_day, at, booking_url, source_url in rows:
        start = show_datetime(show_day, at)
        if show_day == day and start < now:
            continue  # already started
        starts = (
            upcoming.setdefault(film_id, {}).setdefault(show_day, {}).setdefault((cinema_name, slug), {}).setdefault(sala, {})
        )
        starts[start] = _show_url(booking_url, source_url, cinema_url)
        firsts = first_by_cinema.setdefault(film_id, {})
        if cinema_name not in firsts or show_day < firsts[cinema_name]:
            firsts[cinema_name] = show_day

    announced: dict[int, dict[str, list[date]]] = {}
    for film_id, cinema_name, release in (
        db.query(ComingSoon.film_id, Cinema.name, ComingSoon.release_date)
        .join(Cinema, Cinema.id == ComingSoon.cinema_id)
        .filter(ComingSoon.film_id.in_(cards))
        .filter(Cinema.slug == cinema_slug if cinema_slug else True)
    ):
        announced.setdefault(film_id, {}).setdefault(cinema_name, [])
        if release:
            announced[film_id][cinema_name].append(release)

    for film_id, card in cards.items():
        by_day = upcoming.get(film_id, {})
        if by_day:
            card.next_day = min(by_day)
            card.next_is_today = card.next_day == day
            for (cinema_name, slug), by_sala in by_day[card.next_day].items():
                card.next_shows.append(CinemaToday(cinema=cinema_name, slug=slug, salas=_group_by_sala(by_sala, card.film)))
            card.next_shows.sort(key=lambda c: (c.salas[0].first_start, c.cinema))

        shows = first_by_cinema.get(film_id, {})
        card.has_shows = bool(shows)
        releases = [CinemaRelease(cinema=name, first_date=d) for name, d in shows.items()]
        for name, dates in announced.get(film_id, {}).items():
            if name not in shows:
                releases.append(CinemaRelease(cinema=name, first_date=min(dates, default=None), announced=True))
        releases.sort(key=lambda c: (c.first_date is None, c.first_date or date.max, c.cinema))
        card.cinemas = releases
        card.first_date = min((c.first_date for c in releases if c.first_date), default=None)
    return list(cards.values())


def _title_matches(film: Film, query: str) -> bool:
    """The search box: the words typed appear in the title (TMDB or the cinema's), ignoring accents."""
    needle = normalize_title(query)
    titles = (film.raw_title, film.tmdb_title if film.is_tmdb_confirmed else None)
    return any(needle in normalize_title(t) for t in titles if t)


def _filter_url(path: str, current: dict[str, str | None], **changes: str | None) -> str:
    """The page with its filters, some of them changed (None removes one)."""
    params = {k: v for k, v in {**current, **changes}.items() if v}
    return path + (f"?{urlencode(params)}" if params else "")


def _first_show_days(db: Session, film_ids: list[int]) -> dict[int, date]:
    """First day each film was screened in a cinema of the area (its "uscita" here)."""
    if not film_ids:
        return {}
    return dict(
        db.query(Showtime.film_id, func.min(Showtime.date)).filter(Showtime.film_id.in_(film_ids)).group_by(Showtime.film_id)
    )


def _exit_date(film: Film) -> date | None:
    """Day a film no longer programmed becomes "uscito" if it does not come back."""
    if film.last_seen_date is None:
        return None
    is_event = is_event_film(film, today=_now().date())
    threshold = settings.SYNC_DAYS_TO_USCITO_EVENTO if is_event else settings.SYNC_DAYS_TO_USCITO
    return film.last_seen_date + timedelta(days=threshold)


def _films_with_upcoming_shows(db: Session, now: datetime) -> set[int]:
    day = programme_day(now)
    return {
        film_id
        for film_id, show_day, at in db.query(Showtime.film_id, Showtime.date, Showtime.time).filter(Showtime.date >= day)
        if show_day > day or show_datetime(show_day, at) >= now
    }


def _nav_counts(db: Session) -> dict[str, int]:
    upcoming = _films_with_upcoming_shows(db, _now())
    announced = {film_id for (film_id,) in db.query(ComingSoon.film_id).distinct()}
    in_sala = {film_id for (film_id,) in db.query(Film.id).filter_by(status="in_sala")}
    in_uscita = {film_id for (film_id,) in db.query(Film.id).filter_by(status="in_uscita")}
    return {
        "in_sala": len(in_sala & upcoming),
        "in_uscita": len(in_uscita & (upcoming | announced)),
        "da_verificare": db.query(Film).filter(Film.tmdb_match_status.in_(REVIEW_STATUSES)).count(),
        # Only what is still to export: films already imported on Letterboxd are done
        "watchlist": db.query(Film)
        .filter(Film.status == "uscito", Film.vote.in_(["V", "?"]), Film.letterboxd_exported.is_(False))
        .count(),
        "visti": len(export_service.diary_exportable(db)),
    }


@dataclass
class CinemaMenuItem:
    slug: str
    name: str
    films_today: int  # films with shows still to come today


def _cinema_menu(db: Session, now: datetime) -> list[CinemaMenuItem]:
    """The cinemas of the left menu, with how many films they still show today."""
    day = programme_day(now)
    films_today: dict[int, set[int]] = {}
    for cinema_id, film_id, show_day, at in db.query(
        Showtime.cinema_id, Showtime.film_id, Showtime.date, Showtime.time
    ).filter(Showtime.date == day):
        if show_datetime(show_day, at) >= now:
            films_today.setdefault(cinema_id, set()).add(film_id)
    return [
        CinemaMenuItem(slug=c.slug, name=c.name, films_today=len(films_today.get(c.id, ())))
        for c in db.query(Cinema).order_by(Cinema.name)
    ]


def _v_arrivals(db: Session, now: datetime) -> list[Film]:
    """Films voted V that arrived in theaters and whose notice was not dismissed yet."""
    films = (
        db.query(Film)
        .filter(Film.status == "in_sala", Film.vote == "V", Film.in_sala_noticed.is_(False))
        .all()
    )
    upcoming = _films_with_upcoming_shows(db, now) if films else set()
    return sorted((f for f in films if f.id in upcoming), key=lambda f: _film_title(f).lower())


def _film_title(film: Film) -> str:
    return film.tmdb_title if film.is_tmdb_confirmed and film.tmdb_title else film.raw_title


def _render(request: Request, db: Session, name: str, active: str, **context) -> HTMLResponse:
    now = _now()
    context.update(
        active=active, counts=_nav_counts(db), today=now.date(), votes=VOTES, cinema_menu=_cinema_menu(db, now),
        programme_day=programme_day(now), arrivals=_v_arrivals(db, now), film_title=_film_title,
    )
    return templates.TemplateResponse(request, name, context)


def _get_film(db: Session, film_id: int) -> Film:
    film = db.get(Film, film_id)
    if film is None:
        raise HTTPException(status_code=404, detail="Film non trovato")
    return film


def _is_htmx(request: Request) -> bool:
    return request.headers.get("HX-Request") == "true"


def _safe_path(value: str | None) -> str | None:
    """A path inside the app ("/in-uscita"), or None: never a link to another site."""
    if not value:
        return None
    parts = urlsplit(value)
    if parts.scheme or parts.netloc or not parts.path.startswith("/") or parts.path.startswith("//"):
        return None
    return parts.path + (f"?{parts.query}" if parts.query else "")


# ------------------------------------------------------------------
# Pages
# ------------------------------------------------------------------


@router.get("/favicon.ico", include_in_schema=False)
def favicon():
    """The CNV icon, also used by the desktop shortcut."""
    return FileResponse(STATIC_DIR / "cnv.ico", media_type="image/x-icon")


@router.get("/", response_class=HTMLResponse)
def index(
    request: Request,
    voto: str | None = Query(None),
    genere: str | None = Query(None),
    cinema: str | None = Query(None),
    q: str | None = Query(None),
    db: Session = Depends(get_db),
):
    """Home page – films in theaters, filtered by vote, genre, cinema and title.

    Films without upcoming screenings are listed apart: they are only waiting out the
    tolerance days before becoming "uscito". With a cinema chosen only its shows count.
    """
    in_sala = db.query(Film).filter_by(status="in_sala").all()
    genres = sorted({f.genre for f in in_sala if f.has_tmdb_details and f.genre})
    if voto not in VOTE_FILTERS:
        voto = None
    if genere not in genres:
        genere = None
    if cinema and db.query(Cinema).filter_by(slug=cinema).first() is None:
        cinema = None
    q = (q or "").strip() or None

    films = [
        f for f in in_sala
        if (voto is None or f.vote == VOTE_FILTERS[voto])
        and (genere is None or (f.has_tmdb_details and f.genre == genere))
        and (q is None or _title_matches(f, q))
    ]
    cards = _film_cards(db, films, _now(), cinema_slug=cinema)
    since = _first_show_days(db, [c.film.id for c in cards])
    for card in cards:
        card.in_sala_since = since.get(card.film.id)
    # Most recent arrivals first, then alphabetical
    showing = sorted(
        (c for c in cards if c.has_shows),
        key=lambda c: (-(c.in_sala_since or date.min).toordinal(), c.title.lower()),
    )
    # With a cinema chosen, films not on there are simply left out
    gone = [] if cinema else sorted((c for c in cards if not c.has_shows), key=lambda c: c.title.lower())
    for card in gone:
        card.exit_date = _exit_date(card.film)
    filters = {"voto": voto, "genere": genere, "cinema": cinema, "q": q}
    not_updated = [(c, d) for c, d in cinemas_not_updated(db) if cinema in (None, c.slug)]
    return _render(
        request, db, "index.html", "in_sala", cards=showing, gone=gone, voto=voto, filters=filters, genres=genres,
        not_updated=not_updated,
        filter_url=lambda **changes: _filter_url("/", filters, **changes),
    )


@dataclass
class CinemaDayFilm:
    film: Film
    salas: list[SalaShows]

    @property
    def title(self) -> str:
        return self.film.tmdb_title if self.film.is_tmdb_confirmed and self.film.tmdb_title else self.film.raw_title


@router.get("/cinema/{slug}", response_class=HTMLResponse)
def cinema_page(request: Request, slug: str, giorno: str | None = Query(None), db: Session = Depends(get_db)):
    """One cinema: the shows of a day (today by default) and the days it has programmed.

    Only days the cinema's site lists appear in the calendar; today shows only what
    has not started yet. Each time opens the cinema's page to buy the ticket.
    """
    cinema = db.query(Cinema).filter_by(slug=slug).first()
    if cinema is None:
        raise HTTPException(status_code=404, detail="Cinema non trovato")
    now = _now()
    first_day = programme_day(now)

    by_day: dict[date, dict[int, dict[str | None, dict[datetime, str]]]] = {}
    for show in db.query(Showtime).filter(Showtime.cinema_id == cinema.id, Showtime.date >= first_day):
        start = show_datetime(show.date, show.time)
        if show.date == first_day and start < now:
            continue  # already started
        starts = by_day.setdefault(show.date, {}).setdefault(show.film_id, {}).setdefault(show.sala, {})
        starts[start] = _show_url(show.booking_url, show.source_url, cinema.url)

    days = sorted(by_day)
    try:
        selected = date.fromisoformat(giorno) if giorno else None
    except ValueError:
        selected = None
    if selected not in by_day:
        selected = days[0] if days else None
        # Opened without choosing a day and nothing left today: say these are a later day's
        today_over = selected is not None and selected != first_day
    else:
        today_over = False

    films: list[CinemaDayFilm] = []
    if selected is not None:
        film_objs = {f.id: f for f in db.query(Film).filter(Film.id.in_(by_day[selected]))}
        films = [
            CinemaDayFilm(film=film_objs[film_id], salas=_group_by_sala(by_sala, film_objs[film_id]))
            for film_id, by_sala in by_day[selected].items()
            if film_id in film_objs
        ]
        films.sort(key=lambda f: (min(s.first_start for s in f.salas), f.title.lower()))

    return _render(
        request, db, "cinema.html", f"cinema:{slug}",
        cinema=cinema, days=days, selected=selected, first_day=first_day, films=films, today_over=today_over,
        not_updated=[(c, d) for c, d in cinemas_not_updated(db) if c.id == cinema.id],
    )


@dataclass
class FilmDay:
    day: date
    salas: list[SalaShows]


@dataclass
class FilmCinema:
    name: str
    slug: str
    days: list[FilmDay]


@router.get("/film/{film_id}", response_class=HTMLResponse)
def film_page(request: Request, film_id: int, db: Session = Depends(get_db)):
    """One film: every show still to come, day by day, split by cinema."""
    film = _get_film(db, film_id)
    now = _now()
    first_day = programme_day(now)

    by_cinema: dict[tuple[str, str], dict[date, dict[str | None, dict[datetime, str]]]] = {}
    rows = (
        db.query(Showtime, Cinema)
        .join(Cinema, Cinema.id == Showtime.cinema_id)
        .filter(Showtime.film_id == film.id, Showtime.date >= first_day)
    )
    for show, cinema in rows:
        start = show_datetime(show.date, show.time)
        if show.date == first_day and start < now:
            continue  # already started
        starts = by_cinema.setdefault((cinema.name, cinema.slug), {}).setdefault(show.date, {}).setdefault(show.sala, {})
        starts[start] = _show_url(show.booking_url, show.source_url, cinema.url)
    cinemas = [
        FilmCinema(
            name=name,
            slug=slug,
            days=[FilmDay(day=d, salas=_group_by_sala(by_sala, film)) for d, by_sala in sorted(days.items())],
        )
        for (name, slug), days in by_cinema.items()
    ]
    cinemas.sort(key=lambda c: (c.days[0].salas[0].first_start, c.name))

    card = _film_cards(db, [film], now)[0]
    card.in_sala_since = _first_show_days(db, [film.id]).get(film.id)
    if not card.has_shows and film.status == "in_sala":
        card.exit_date = _exit_date(film)
    return _render(request, db, "film.html", "film", card=card, cinemas=cinemas)


@router.get("/in-uscita", response_class=HTMLResponse)
def coming_soon(
    request: Request,
    q: str | None = Query(None),
    vista: str | None = Query(None),
    mese: str | None = Query(None),
    db: Session = Depends(get_db),
):
    """Films not in theaters yet: future screenings or announced by a cinema, soonest first.

    ``vista=calendario`` shows them on a month calendar (``mese=YYYY-MM``, this month by default).
    """
    q = (q or "").strip() or None
    films = [f for f in db.query(Film).filter_by(status="in_uscita") if q is None or _title_matches(f, q)]
    cards = sorted(
        (c for c in _film_cards(db, films, _now()) if c.cinemas),
        key=lambda c: (c.first_date is None, c.first_date or date.max, c.title.lower()),
    )
    view = "calendario" if vista == "calendario" else "elenco"
    context = {"cards": cards, "q": q, "view": view}
    if view == "calendario":
        context["month"] = _release_month(cards, mese, _now().date())
    return _render(request, db, "in_uscita.html", "in_uscita", **context)


@dataclass
class ReleaseMonth:
    first: date  # first day of the month shown
    weeks: list[list[date]]  # Monday to Sunday, including the days of nearby months that fill the weeks
    releases: dict[date, list[FilmCard]]  # films by their first date
    undated: list[FilmCard]
    prev: str | None  # "YYYY-MM" of the previous month, None before the current one
    next: str | None  # "YYYY-MM" of the next month, None after the last release

    @property
    def title(self) -> str:
        return f"{MONTHS[self.first.month - 1]} {self.first.year}"


def _release_month(cards: list[FilmCard], month: str | None, today: date) -> ReleaseMonth:
    """The month calendar of the coming releases."""
    this_month = today.replace(day=1)
    try:
        first = date.fromisoformat(f"{month}-01") if month else this_month
    except ValueError:
        first = this_month
    first = max(first, this_month)
    releases: dict[date, list[FilmCard]] = {}
    for card in cards:
        if card.first_date:
            releases.setdefault(card.first_date, []).append(card)
    last_release = max(releases, default=today)
    next_first = (first.replace(day=28) + timedelta(days=4)).replace(day=1)
    prev_first = (first - timedelta(days=1)).replace(day=1)
    return ReleaseMonth(
        first=first,
        weeks=calendar.Calendar(firstweekday=0).monthdatescalendar(first.year, first.month),
        releases=releases,
        undated=[c for c in cards if not c.first_date],
        prev=prev_first.strftime("%Y-%m") if first > this_month else None,
        next=next_first.strftime("%Y-%m") if next_first <= last_release else None,
    )


@router.get("/da-verificare", response_class=HTMLResponse)
def review(request: Request, db: Session = Depends(get_db)):
    """Films whose TMDB match is uncertain or missing."""
    films = (
        db.query(Film)
        .filter(Film.tmdb_match_status.in_(REVIEW_STATUSES))
        .order_by(Film.tmdb_match_status, Film.raw_title)
        .all()
    )
    cards = _film_cards(db, films, _now())
    return _render(request, db, "da_verificare.html", "da_verificare", cards=cards, tmdb_enabled=bool(settings.TMDB_API_KEY))


@router.get("/watchlist", response_class=HTMLResponse)
def watchlist(request: Request, db: Session = Depends(get_db)):
    """Films that left theaters and were marked V or ?, split by Letterboxd export state."""
    return _render(
        request, db, "watchlist.html", "watchlist",
        to_export=[FilmCard(film=f) for f in export_service.exportable_films(db)],
        missing_tmdb=export_service.films_missing_tmdb(db),
        exported=export_service.exported_films(db),
    )


@router.get("/stato", response_class=HTMLResponse)
def status_page(request: Request, db: Session = Depends(get_db)):
    """Sync history, last scrape of each cinema, backups and automatic sync."""
    cinemas = []
    for cinema in db.query(Cinema).order_by(Cinema.name):
        runs = (
            db.query(SyncRun).filter_by(cinema_id=cinema.id).order_by(SyncRun.created_at.desc()).limit(5).all()
        )
        cinemas.append({"cinema": cinema, "runs": runs})
    scheduler = request.app.state.scheduler
    return _render(
        request, db, "stato.html", "stato",
        logs=db.query(SyncLog).order_by(SyncLog.started_at.desc()).limit(15).all(),
        cinemas=cinemas,
        backups=list_backups(settings.BACKUPS_DIR),
        backups_dir=settings.BACKUPS_DIR,
        backups_keep=settings.BACKUPS_KEEP,
        log_file=settings.LOGS_DIR / LOG_FILE_NAME,
        scheduler=scheduler,
        auto_sync=settings.AUTO_SYNC_ENABLED,
        auto_sync_time=settings.AUTO_SYNC_TIME,
        running=is_sync_running(db),
    )


def _vote_box(request: Request, film: Film, ask_cinema: list[Cinema] | None = None) -> HTMLResponse:
    return templates.TemplateResponse(
        request, "_vote.html", {"film": film, "votes": VOTES, "today": _now().date(), "ask_cinema": ask_cinema}
    )


def _seen_cinema_choices(db: Session, film: Film, day: date) -> list[Cinema]:
    """Cinemas where the film was shown in the last month (up to today): where it was probably seen."""
    cinemas = (
        db.query(Cinema)
        .join(Showtime, Showtime.cinema_id == Cinema.id)
        .filter(Showtime.film_id == film.id, Showtime.date <= day, Showtime.date >= day - timedelta(days=30))
        .distinct()
        .order_by(Cinema.name)
        .all()
    )
    return cinemas or db.query(Cinema).order_by(Cinema.name).all()


@router.post("/film/{film_id}/vote", response_class=HTMLResponse)
def vote_film(request: Request, film_id: int, v: str = Form(""), db: Session = Depends(get_db)):
    """Save a vote (V / ? / S = seen). Clicking the current vote again removes it. Returns an htmx partial.

    Marking a film seen records the day (the programme day: after midnight, last night) and
    asks in which cinema.
    """
    film = _get_film(db, film_id)
    if v not in (*VOTES, ""):
        raise HTTPException(status_code=422, detail="Voto non valido")
    film.vote = None if v in ("", film.vote) else v
    if film.vote == "V" and film.status == "in_sala":
        film.in_sala_noticed = True  # voted while in sala: no notice needed
    ask_cinema = None
    if film.vote == "S":
        film.seen_on = programme_day(_now())
        film.seen_cinema_id = None
        ask_cinema = _seen_cinema_choices(db, film, film.seen_on)
    else:
        film.seen_on, film.seen_cinema_id, film.diary_exported = None, None, False
    db.commit()
    return _vote_box(request, film, ask_cinema)


@router.post("/film/{film_id}/visto-dove", response_class=HTMLResponse)
def seen_where(request: Request, film_id: int, cinema: str = Form(""), db: Session = Depends(get_db)):
    """The cinema where a seen film was watched (empty: skipped). Returns the vote partial."""
    film = _get_film(db, film_id)
    chosen = db.query(Cinema).filter_by(slug=cinema).first() if cinema else None
    film.seen_cinema_id = chosen.id if chosen else None
    db.commit()
    return _vote_box(request, film)


@router.post("/film/{film_id}/visto")
def edit_seen(
    film_id: int, seen_on: str = Form(""), cinema: str = Form(""), db: Session = Depends(get_db)
):
    """Change the day and cinema of a seen film (from the "Visti" page)."""
    film = _get_film(db, film_id)
    if film.vote != "S":
        raise HTTPException(status_code=409, detail="Il film non è segnato come visto")
    try:
        film.seen_on = date.fromisoformat(seen_on) if seen_on else film.seen_on
    except ValueError:
        raise HTTPException(status_code=422, detail="Data non valida") from None
    chosen = db.query(Cinema).filter_by(slug=cinema).first() if cinema else None
    film.seen_cinema_id = chosen.id if chosen else None
    db.commit()
    return RedirectResponse("/visti", status_code=303)


@router.get("/visti", response_class=HTMLResponse)
def seen_page(request: Request, db: Session = Depends(get_db)):
    """Films marked seen: day and cinema (editable) and the export to the Letterboxd diary."""
    seen = export_service.seen_films(db)
    return _render(
        request, db, "visti.html", "visti",
        seen=seen,
        to_export=[f for f in seen if not f.diary_exported and f.is_tmdb_confirmed],
        missing_tmdb=[f for f in seen if not f.diary_exported and not f.is_tmdb_confirmed],
        cinemas=db.query(Cinema).order_by(Cinema.name).all(),
    )


@router.get("/visti/diario.csv")
def export_diary(db: Session = Depends(get_db)):
    """Download the Letterboxd diary CSV (does not mark anything as exported)."""
    return StreamingResponse(
        iter([export_service.export_diary_csv(db)]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename=letterboxd_diario_{_now():%Y-%m-%d}.csv"},
    )


@router.post("/visti/esportati")
def mark_diary_exported(film_ids: list[int] = Form(default=[]), db: Session = Depends(get_db)):
    """The user imported the diary CSV on Letterboxd."""
    export_service.mark_diary_exported(db, film_ids)
    db.commit()
    return RedirectResponse("/visti", status_code=303)


@router.post("/film/{film_id}/diario-di-nuovo")
def diary_again(film_id: int, db: Session = Depends(get_db)):
    export_service.mark_diary_exported(db, [_get_film(db, film_id).id], exported=False)
    db.commit()
    return RedirectResponse("/visti", status_code=303)


@router.post("/avviso-in-sala/visto")
def dismiss_arrivals(
    request: Request, ids: list[int] = Form(default=[]), dopo: str = Form(""), db: Session = Depends(get_db)
):
    """Hide the "now in sala" notice for the films it listed (not for ones arrived meanwhile)."""
    for film in db.query(Film).filter(Film.id.in_(ids)):
        film.in_sala_noticed = True
    db.commit()
    if _is_htmx(request):
        return HTMLResponse("")
    return RedirectResponse(_safe_path(dopo) or "/", status_code=303)


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
    dopo: str = Query(""),
    db: Session = Depends(get_db),
    tmdb: TmdbClient | None = Depends(get_tmdb),
):
    """Search TMDB with the user's query and return candidates as an htmx partial.

    ``dopo`` is the page to go back to once a candidate is chosen (the "cambia
    abbinamento" page); without it the review card simply disappears.
    """
    film = _get_film(db, film_id)
    context: dict = {
        "film": film,
        "candidates": [],
        "error": None,
        "query": q.strip(),
        "next_url": _safe_path(dopo),
    }
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
    dopo: str = Form(""),
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

    next_url = _safe_path(dopo)
    if next_url:
        if _is_htmx(request):
            return Response(status_code=200, headers={"HX-Redirect": next_url})
        return RedirectResponse(next_url, status_code=303)
    return Response(status_code=200) if _is_htmx(request) else RedirectResponse("/da-verificare", status_code=303)


@router.get("/film/{film_id}/abbinamento", response_class=HTMLResponse)
def change_match(request: Request, film_id: int, db: Session = Depends(get_db)):
    """Fix a wrong TMDB match: search the right film and choose it."""
    film = _get_film(db, film_id)
    # Back to the CNV page the user came from (never to another site)
    ref = urlsplit(request.headers.get("referer") or "")
    from_cnv = ref.netloc == request.headers.get("host")
    referer = _safe_path(ref.path + (f"?{ref.query}" if ref.query else "")) if from_cnv else None
    back = referer if referer and "/abbinamento" not in referer else "/"
    return _render(
        request, db, "abbinamento.html", "", film=film, back=back, tmdb_enabled=bool(settings.TMDB_API_KEY)
    )


@router.get("/export")
def export_csv(db: Session = Depends(get_db)):
    """Download the Letterboxd watchlist CSV (does not mark anything as exported)."""
    csv_content = export_service.export_letterboxd_csv(db)
    filename = f"letterboxd_watchlist_{_now():%Y-%m-%d}.csv"
    return StreamingResponse(
        iter([csv_content]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@router.post("/watchlist/esportati")
def mark_as_exported(film_ids: list[int] = Form(default=[]), db: Session = Depends(get_db)):
    """The user imported the CSV on Letterboxd: mark those films as exported."""
    export_service.mark_exported(db, film_ids)
    db.commit()
    return RedirectResponse("/watchlist", status_code=303)


@router.post("/film/{film_id}/esporta-di-nuovo")
def export_again(film_id: int, db: Session = Depends(get_db)):
    export_service.unmark_exported(db, _get_film(db, film_id))
    db.commit()
    return RedirectResponse("/watchlist", status_code=303)


@router.post("/sync")
async def trigger_sync(request: Request, db: Session = Depends(get_db)):
    """Run a full sync (backup, scrapers, TMDB matching) and go back to the previous page."""
    # Only the path of the referring page, so the redirect never leaves the app
    back = urlsplit(request.headers.get("referer") or "").path or "/"
    try:
        await run_full_sync(db, "manuale")
    except SyncAlreadyRunning:
        return RedirectResponse(url="/stato?occupato=1", status_code=303)
    return RedirectResponse(url=back, status_code=303)
