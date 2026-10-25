"""TMDB matching – links each film to a TMDB id and merges duplicates sharing the same id.

Flow for every film not yet checked:
  1. build_search_query() strips cinema noise (4K, V.O., RIED., "30° ANNIVERSARIO", ...)
     that makes TMDB return nothing, and keeps hints (re-release, anniversary year).
  2. Candidates from TMDB are scored on title similarity, release date and popularity.
  3. A clear winner becomes "abbinato"; an uncertain one is stored as a suggestion
     with status "da_verificare"; no result at all means "non_trovato" (retried later).
  4. When an "abbinato" film shares its TMDB id with another confirmed film, the two
     are merged and the old title is kept as a FilmAlias.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from difflib import SequenceMatcher
import logging
import re

import httpx
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.db.models import ComingSoon, DailySnapshot, Film, FilmAlias, Showtime
from app.services.tmdb import MovieSearcher, TmdbMovie
from app.services.titles import normalize_title

logger = logging.getLogger(__name__)

STATUS_MATCHED = "abbinato"
STATUS_REVIEW = "da_verificare"
STATUS_NOT_FOUND = "non_trovato"
STATUS_MANUAL = "manuale"

AUTO_MIN_SIMILARITY = 0.85  # below this the best candidate always goes to review
AUTO_MIN_MARGIN = 0.08  # score gap required between best and runner-up
NOT_FOUND_RETRY_DAYS = 7
MAX_RESULTS_PER_QUERY = 10
MAX_CONSECUTIVE_API_ERRORS = 3

_ANNIVERSARY = re.compile(
    r"\b(?P<years>\d{1,3})\s*(?:°|º|th|st|nd|rd)?\s*anniversar(?:io|y)\b",
    flags=re.IGNORECASE,
)

# Markers of a re-release of an old film: removed from the query, they disable the
# "recent release" preference.
_REISSUE_MARKERS = [
    r"\(\s*ried\.?\s*\)",
    r"\bried(?:izione\b|\.)",
    r"\b[48]\s*k\b",
    r"\b(?:versione\s+)?restaurat[oa]\b",
    r"\bremaster(?:ed|izzato)?\b",
    r"\bdirector'?s\s+cut\b",
    r"\banniversar(?:io|y)\b",
]

# Screening details that are not part of the title.
_NOISE_MARKERS = [
    r"\bv\s*\.\s*o\s*\.?",
    r"\bvos\b",
    r"\bsub(?:titolato)?\s+ita\b",
    r"\b(?:in\s+)?lingua\s+originale\b",
    r"\b[23]d\b",
    r"\bimax\b",
    r"\binfinity\s+vision\b",
]
# A trailing year ("GODZILLA MINUS ZERO IMAX 2026") is a hint, not part of the title
_TRAILING_YEAR = re.compile(r"\s(?P<year>(?:19|20)\d{2})\s*$")


@dataclass
class SearchQuery:
    """What to send to TMDB for one film, plus hints for scoring."""

    queries: list[str]  # most specific first
    compare_titles: list[str]  # normalized titles compared with each candidate
    year_hint: int | None = None
    is_reissue: bool = False


@dataclass
class ScoredCandidate:
    movie: TmdbMovie
    similarity: float
    score: float


@dataclass
class MatchDecision:
    status: str  # STATUS_MATCHED | STATUS_REVIEW | STATUS_NOT_FOUND
    best: ScoredCandidate | None = None
    candidates: list[ScoredCandidate] = field(default_factory=list)


@dataclass
class MatchReport:
    """Summary of a matching pass."""

    matched: list[Film] = field(default_factory=list)
    to_review: list[Film] = field(default_factory=list)
    not_found: list[Film] = field(default_factory=list)
    merges: dict[int, int] = field(default_factory=dict)  # merged film id -> surviving film id
    merged_titles: list[tuple[str, str]] = field(default_factory=list)  # (merged title, surviving title)
    errors: list[str] = field(default_factory=list)


# ------------------------------------------------------------------
# Query building and scoring
# ------------------------------------------------------------------


def _tidy(text: str) -> str:
    text = re.sub(r"\(\s*\)", "", text)
    text = re.sub(r"\s+", " ", text)
    return re.sub(r"^[-–—:\s]+|[-–—:\s]+$", "", text).strip()


def build_search_query(title: str, reference_date: date) -> SearchQuery:
    """Turn a cleaned cinema title into TMDB queries.

    Examples:
        - "MATRIX 4K" -> queries ["MATRIX"], re-release
        - "TRAINSPOTTING 30° ANNIVERSARIO" -> ["TRAINSPOTTING"], year hint 30 years ago
        - "mammina (other mommy)" -> ["mammina", "other mommy"]
    """
    t = title
    year_hint = None
    is_reissue = False

    m = _ANNIVERSARY.search(t)
    if m:
        year_hint = reference_date.year - int(m.group("years"))
        is_reissue = True
        t = t[: m.start()] + t[m.end() :]

    for pattern in _REISSUE_MARKERS:
        t, n = re.subn(pattern, " ", t, flags=re.IGNORECASE)
        is_reissue = is_reissue or n > 0
    for pattern in _NOISE_MARKERS:
        t = re.sub(pattern, " ", t, flags=re.IGNORECASE)
    m = _TRAILING_YEAR.search(_tidy(t))
    # Only a year close to now: "BLADE RUNNER 2049" or "1917" are titles
    if m and year_hint is None and abs(int(m.group("year")) - reference_date.year) <= 1:
        year_hint = int(m.group("year"))
        t = _tidy(t)[: m.start()]

    queries: list[str] = []
    alt = re.search(r"\(([^()]+)\)", t)
    base = _tidy(t[: alt.start()] + t[alt.end() :]) if alt else _tidy(t)
    for q in (base, _tidy(alt.group(1)) if alt else ""):
        if q and q not in queries:
            queries.append(q)
    if not queries:
        queries.append(title)

    compare = [normalize_title(q) for q in queries]
    return SearchQuery(queries=queries, compare_titles=compare, year_hint=year_hint, is_reissue=is_reissue)


def _similarity(a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a, b).ratio()


def _date_score(movie: TmdbMovie, sq: SearchQuery, reference_date: date) -> float:
    if sq.year_hint:
        return 1.0 if movie.year and abs(movie.year - sq.year_hint) <= 1 else 0.0
    if sq.is_reissue:
        return 0.5
    if movie.release_date is None:
        return 0.3
    days = abs((movie.release_date - reference_date).days)
    if days <= 180:
        return 1.0
    if days >= 3 * 365:
        return 0.0
    return 1.0 - (days - 180) / (3 * 365 - 180)


def score_candidates(movies: list[TmdbMovie], sq: SearchQuery, reference_date: date) -> list[ScoredCandidate]:
    """Score candidates: 70% title similarity, 20% release date, 10% relative popularity."""
    max_pop = max((m.popularity for m in movies), default=0.0) or 1.0
    scored = []
    for movie in movies:
        names = [normalize_title(movie.title), normalize_title(movie.original_title)]
        sim = max(_similarity(q, n) for q in sq.compare_titles for n in names)
        score = 0.7 * sim + 0.2 * _date_score(movie, sq, reference_date) + 0.1 * (movie.popularity / max_pop)
        scored.append(ScoredCandidate(movie=movie, similarity=sim, score=score))
    return sorted(scored, key=lambda c: c.score, reverse=True)


def decide(candidates: list[ScoredCandidate]) -> MatchDecision:
    """Accept the best candidate only when it is similar enough and clearly ahead."""
    if not candidates:
        return MatchDecision(status=STATUS_NOT_FOUND)
    best = candidates[0]
    runner = candidates[1] if len(candidates) > 1 else None
    clear_winner = (
        runner is None
        or best.score - runner.score >= AUTO_MIN_MARGIN
        # An exact title beats candidates that only partially match it
        or (best.similarity >= 0.999 and runner.similarity < 0.95)
    )
    status = STATUS_MATCHED if best.similarity >= AUTO_MIN_SIMILARITY and clear_winner else STATUS_REVIEW
    return MatchDecision(status=status, best=best, candidates=candidates)


async def search_candidates(searcher: MovieSearcher, sq: SearchQuery) -> list[TmdbMovie]:
    """Collect unique candidates for all queries (with the year hint first, when present)."""
    found: dict[int, TmdbMovie] = {}
    for query in sq.queries:
        results: list[TmdbMovie] = []
        if sq.year_hint:
            results = await searcher.search_movies(query, year=sq.year_hint)
        if not results:
            results = await searcher.search_movies(query)
        for movie in results[:MAX_RESULTS_PER_QUERY]:
            found.setdefault(movie.id, movie)
    return list(found.values())


# ------------------------------------------------------------------
# Applying matches and merging duplicates
# ------------------------------------------------------------------


def _reference_date(db: Session, film: Film, today: date) -> date:
    """When the film is (or will be) on screen: first showtime, else announced release, else today."""
    first_show = min((s.date for s in film.showtimes), default=None)
    announced = min((c.release_date for c in film.coming_soon if c.release_date), default=None)
    return first_show or announced or today


def _apply_movie(film: Film, movie: TmdbMovie, status: str, confidence: float, now: datetime) -> None:
    film.tmdb_id = movie.id
    film.tmdb_title = movie.title
    film.year = movie.year
    film.poster_url = movie.poster_url
    film.tmdb_match_status = status
    film.tmdb_confidence = round(confidence, 3)
    film.tmdb_checked_at = now


def _utc_naive(value: datetime | None) -> datetime | None:
    """UTC timestamps without tzinfo, as SQLite returns them: freshly created rows carry tzinfo."""
    if value is not None and value.tzinfo is not None:
        return value.astimezone(timezone.utc).replace(tzinfo=None)
    return value


def _latest(a: datetime | None, b: datetime | None) -> datetime | None:
    values = [v for v in (_utc_naive(a), _utc_naive(b)) if v is not None]
    return max(values, default=None)


def _earliest(a: datetime | None, b: datetime | None) -> datetime | None:
    values = [v for v in (_utc_naive(a), _utc_naive(b)) if v is not None]
    return min(values, default=None)


def merge_films(db: Session, survivor: Film, other: Film) -> None:
    """Move everything from ``other`` into ``survivor`` and delete ``other``.

    Showtimes and daily snapshots are moved (duplicates collapsed), the user's vote is
    kept, and other's titles become aliases of survivor so future scrapes land on it.
    """
    db.flush()

    survivor_shows = {
        (s.cinema_id, s.date, s.time, s.sala): s for s in db.query(Showtime).filter_by(film_id=survivor.id)
    }
    for show in db.query(Showtime).filter_by(film_id=other.id).all():
        twin = survivor_shows.get((show.cinema_id, show.date, show.time, show.sala))
        if twin is not None:
            twin.last_seen = _latest(twin.last_seen, show.last_seen)
            db.delete(show)
        else:
            show.film_id = survivor.id

    survivor_coming = {
        (c.cinema_id, c.source): c for c in db.query(ComingSoon).filter_by(film_id=survivor.id)
    }
    for entry in db.query(ComingSoon).filter_by(film_id=other.id).all():
        twin = survivor_coming.get((entry.cinema_id, entry.source))
        if twin is not None:
            dates = [d for d in (twin.release_date, entry.release_date) if d]
            twin.release_date = min(dates) if dates else None
            twin.last_seen = _latest(twin.last_seen, entry.last_seen)
            db.delete(entry)
        else:
            entry.film_id = survivor.id

    survivor_snaps = {
        (s.sync_date, s.cinema_id): s for s in db.query(DailySnapshot).filter_by(film_id=survivor.id)
    }
    for snap in db.query(DailySnapshot).filter_by(film_id=other.id).all():
        twin = survivor_snaps.get((snap.sync_date, snap.cinema_id))
        if twin is not None:
            twin.showtimes_count += snap.showtimes_count
            db.delete(snap)
        else:
            snap.film_id = survivor.id

    # Aliases: other's own title plus any alias it already had
    alias_titles = {other.normalized_title} | {a.normalized_title for a in other.aliases}
    alias_titles.discard(survivor.normalized_title)
    for alias in list(other.aliases):
        db.delete(alias)
    db.flush()
    for title in alias_titles:
        existing = db.query(FilmAlias).filter_by(normalized_title=title).first()
        if existing:
            existing.film_id = survivor.id
        else:
            db.add(FilmAlias(normalized_title=title, film_id=survivor.id))

    # Film fields
    if survivor.vote is None:
        survivor.vote = other.vote
    survivor.first_seen = _earliest(survivor.first_seen, other.first_seen)
    survivor.last_seen = _latest(survivor.last_seen, other.last_seen)
    if other.last_seen_date and (survivor.last_seen_date is None or other.last_seen_date > survivor.last_seen_date):
        survivor.last_seen_date = other.last_seen_date
    # Only an event if both copies were events: a regular run must not get the short threshold
    survivor.is_event = survivor.is_event and other.is_event
    survivor.letterboxd_exported = survivor.letterboxd_exported or other.letterboxd_exported
    survivor.exported_at = _latest(survivor.exported_at, other.exported_at)
    if survivor.status != "uscito" or other.status != "uscito":
        # Still programmed somewhere: the sync recomputes the status right after
        survivor.left_theaters_date = None
    if other.status == "in_sala" and survivor.status != "in_sala":
        survivor.status = "in_sala"
        survivor.in_theaters = True

    db.flush()
    db.expire(other)
    db.expire(survivor, ["showtimes", "snapshots", "aliases", "coming_soon"])
    db.delete(other)
    db.flush()


def _find_confirmed_twin(db: Session, film: Film, tmdb_id: int) -> Film | None:
    return (
        db.query(Film)
        .filter(
            Film.id != film.id,
            Film.tmdb_id == tmdb_id,
            Film.tmdb_match_status.in_([STATUS_MATCHED, STATUS_MANUAL]),
        )
        .order_by(Film.id)
        .first()
    )


def _merge_into_older(db: Session, film: Film, twin: Film) -> tuple[Film, Film]:
    """Merge the newer of the two films into the older one; return (survivor, merged)."""
    survivor, other = (twin, film) if twin.id < film.id else (film, twin)
    logger.info("Unione di '%s' in '%s' (TMDB %s)", other.raw_title, survivor.raw_title, film.tmdb_id)
    merge_films(db, survivor, other)
    return survivor, other


def confirm_match(db: Session, film: Film, movie: TmdbMovie | None = None) -> Film:
    """Confirm a TMDB match chosen by the user ("manuale"), merging any duplicate.

    Without ``movie`` the current suggestion of a "da_verificare" film is confirmed.
    Returns the surviving film (``film`` itself unless it was merged into an older one).
    """
    now = datetime.now(timezone.utc)
    if movie is not None:
        _apply_movie(film, movie, STATUS_MANUAL, 1.0, now)
    elif film.tmdb_id is None:
        raise ValueError("Nessun suggerimento TMDB da confermare")
    else:
        film.tmdb_match_status = STATUS_MANUAL
        film.tmdb_confidence = 1.0
        film.tmdb_checked_at = now

    twin = _find_confirmed_twin(db, film, film.tmdb_id)
    if twin is None:
        db.flush()
        return film
    survivor, _ = _merge_into_older(db, film, twin)
    return survivor


async def search_manual(
    searcher: MovieSearcher, query: str, reference_date: date
) -> list[ScoredCandidate]:
    """Search TMDB with a query typed by the user, ranked like the automatic matching."""
    sq = build_search_query(query, reference_date=reference_date)
    movies = await search_candidates(searcher, sq)
    return score_candidates(movies, sq, reference_date)


def _pending_films(db: Session, now: datetime) -> list[Film]:
    retry_before = now - timedelta(days=NOT_FOUND_RETRY_DAYS)
    return (
        db.query(Film)
        .filter(
            or_(
                Film.tmdb_match_status.is_(None),
                (Film.tmdb_match_status == STATUS_NOT_FOUND)
                & or_(Film.tmdb_checked_at.is_(None), Film.tmdb_checked_at < retry_before),
            )
        )
        .order_by(Film.id)
        .all()
    )


async def match_film(db: Session, film: Film, searcher: MovieSearcher, today: date) -> MatchDecision:
    """Search TMDB for one film and return the decision, without saving it."""
    sq = build_search_query(film.raw_title, reference_date=today)
    movies = await search_candidates(searcher, sq)
    return decide(score_candidates(movies, sq, _reference_date(db, film, today)))


def _record_decision(db: Session, film: Film, decision: MatchDecision, report: MatchReport, now: datetime) -> None:
    """Save one film's TMDB decision, merging it with a confirmed twin if there is one."""
    if decision.status == STATUS_NOT_FOUND:
        film.tmdb_match_status = STATUS_NOT_FOUND
        film.tmdb_checked_at = now
        report.not_found.append(film)
        return

    best = decision.best
    _apply_movie(film, best.movie, decision.status, best.score, now)
    if decision.status == STATUS_REVIEW:
        report.to_review.append(film)
        return

    twin = _find_confirmed_twin(db, film, best.movie.id)
    if twin is None:
        report.matched.append(film)
        return

    older, newer = (twin, film) if twin.id < film.id else (film, twin)
    report.merged_titles.append((newer.raw_title, older.raw_title))
    other_id = newer.id
    if newer in report.matched:
        report.matched.remove(newer)
    survivor, _ = _merge_into_older(db, film, twin)
    report.merges[other_id] = survivor.id
    # Older merges into the deleted film now point at the survivor
    for merged_id, target in report.merges.items():
        if target == other_id:
            report.merges[merged_id] = survivor.id
    if survivor not in report.matched:
        report.matched.append(survivor)


async def match_pending_films(db: Session, searcher: MovieSearcher, today: date | None = None) -> MatchReport:
    """Match every film not yet checked (and retry old "non_trovato"), merging duplicates.

    Each film is saved right after its decision, so the database is never locked while
    waiting for TMDB and the app can save votes during a sync.
    """
    today = today or date.today()
    now = datetime.now(timezone.utc)
    report = MatchReport()
    consecutive_errors = 0

    for film in _pending_films(db, now):
        if film.id in report.merges:
            continue
        try:
            decision = await match_film(db, film, searcher, today)
        except httpx.HTTPError as err:
            msg = f"{film.raw_title}: {err.__class__.__name__}"
            logger.warning("Ricerca TMDB fallita per %s", msg)
            report.errors.append(msg)
            consecutive_errors += 1
            if consecutive_errors >= MAX_CONSECUTIVE_API_ERRORS:
                report.errors.append("Troppi errori consecutivi da TMDB: matching interrotto")
                break
            continue
        consecutive_errors = 0

        _record_decision(db, film, decision, report, now)
        db.commit()

    return report
