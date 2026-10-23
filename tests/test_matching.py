"""Tests for TMDB matching and duplicate merging (TMDB is replaced by a fake searcher)."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone

import httpx
import pytest

from app.config import CinemaConfig
from app.db.models import DailySnapshot, Film, FilmAlias, Showtime
from app.scrapers.base import ShowtimeData
from app.services.matching import (
    STATUS_MATCHED,
    STATUS_NOT_FOUND,
    STATUS_REVIEW,
    build_search_query,
    decide,
    match_pending_films,
    score_candidates,
)
from app.services.sync import run_sync
from app.services.tmdb import TmdbMovie

TODAY = date(2026, 10, 23)

MAMMINA = TmdbMovie(1400837, "Mammina", "Other Mommy", date(2026, 10, 8), 199.5)
MAMMINA_CARA = TmdbMovie(15660, "Mammina cara", "Mommie Dearest", date(1981, 9, 16), 3.5)
RAGIONE_2026 = TmdbMovie(1503762, "Ragione e sentimento", "Sense and Sensibility", date(2026, 10, 22), 122.3)
RAGIONE_1996 = TmdbMovie(4584, "Ragione e sentimento", "Sense and Sensibility", date(1996, 2, 23), 13.6)
TRAINSPOTTING = TmdbMovie(627, "Trainspotting", "Trainspotting", date(1996, 10, 3), 14.9)
T2 = TmdbMovie(180863, "T2 Trainspotting", "T2 Trainspotting", date(2017, 2, 23), 8.0)
MATRIX = TmdbMovie(603, "Matrix", "The Matrix", date(1999, 5, 7), 45.5)
MATRIX_1971 = TmdbMovie(411948, "Matrix", "Matrix", date(1971, 5, 18), 1.3)


class FakeTmdb:
    """Fake searcher: maps lowercase queries to results and records every call."""

    def __init__(self, results: dict[str, list[TmdbMovie]], fail: bool = False) -> None:
        self.results = results
        self.fail = fail
        self.calls: list[tuple[str, int | None]] = []

    async def search_movies(self, query: str, year: int | None = None) -> list[TmdbMovie]:
        self.calls.append((query, year))
        if self.fail:
            raise httpx.ConnectError("offline")
        movies = self.results.get(query.lower(), [])
        if year:
            movies = [m for m in movies if m.year == year]
        return movies


CINEMAS = [
    CinemaConfig(slug="andromeda", name="Andromeda", url="https://example.com", scraper="stub"),
    CinemaConfig(slug="garden", name="Garden", url="https://example.com", scraper="stub"),
]


def show(cinema: str, title: str, day: date, hour: int = 20) -> ShowtimeData:
    return ShowtimeData(cinema=cinema, raw_title=title, date=day, time=time(hour, 0))


# ------------------------------------------------------------------
# Query building
# ------------------------------------------------------------------


@pytest.mark.parametrize(
    ("title", "queries", "year_hint", "is_reissue"),
    [
        ("MATRIX 4K", ["MATRIX"], None, True),
        ("TRAINSPOTTING 30° ANNIVERSARIO", ["TRAINSPOTTING"], 1996, True),
        ("FAST & FURIOUS – 25TH ANNIVERSARY", ["FAST & FURIOUS"], 2001, True),
        ("TRAINSPOTTING (RIED.)", ["TRAINSPOTTING"], None, True),
        ("SHEEP IN THE BOX - V. O.", ["SHEEP IN THE BOX"], None, False),
        ("mammina (other mommy)", ["mammina", "other mommy"], None, False),
        ("DUNE – PARTE TRE", ["DUNE – PARTE TRE"], None, False),
    ],
)
def test_build_search_query(title, queries, year_hint, is_reissue):
    sq = build_search_query(title, reference_date=TODAY)
    assert sq.queries == queries
    assert sq.year_hint == year_hint
    assert sq.is_reissue is is_reissue


# ------------------------------------------------------------------
# Scoring and decision
# ------------------------------------------------------------------


def _decide(title: str, movies: list[TmdbMovie], reference_date: date = TODAY):
    sq = build_search_query(title, reference_date=TODAY)
    return decide(score_candidates(movies, sq, reference_date))


def test_same_title_prefers_the_film_released_now():
    decision = _decide("RAGIONE E SENTIMENTO", [RAGIONE_1996, RAGIONE_2026])
    assert decision.status == STATUS_MATCHED
    assert decision.best.movie.id == RAGIONE_2026.id


def test_anniversary_prefers_the_original_year():
    decision = _decide("TRAINSPOTTING 30° ANNIVERSARIO", [T2, TRAINSPOTTING])
    assert decision.status == STATUS_MATCHED
    assert decision.best.movie.id == TRAINSPOTTING.id


def test_reissue_exact_title_beats_partial_title():
    decision = _decide("TRAINSPOTTING (RIED.)", [TRAINSPOTTING, T2])
    assert decision.status == STATUS_MATCHED
    assert decision.best.movie.id == TRAINSPOTTING.id


def test_reissue_with_homonyms_uses_popularity():
    decision = _decide("MATRIX 4K", [MATRIX_1971, MATRIX])
    assert decision.status == STATUS_MATCHED
    assert decision.best.movie.id == MATRIX.id


def test_ambiguous_candidates_go_to_review():
    twin_a = TmdbMovie(1, "Il Ritorno", "The Return", date(2026, 10, 1), 10.0)
    twin_b = TmdbMovie(2, "Il Ritorno", "Il Ritorno", date(2026, 9, 20), 9.5)
    decision = _decide("IL RITORNO", [twin_a, twin_b])
    assert decision.status == STATUS_REVIEW


def test_low_similarity_goes_to_review():
    decision = _decide("UN TITOLO MAI VISTO", [MAMMINA_CARA])
    assert decision.status == STATUS_REVIEW


def test_no_candidates_is_not_found():
    assert _decide("SCONOSCIUTO", []).status == STATUS_NOT_FOUND


# ------------------------------------------------------------------
# Matching pass on the database
# ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_sync_with_matcher_merges_duplicates(db):
    tmdb = FakeTmdb({"mammina": [MAMMINA, MAMMINA_CARA], "other mommy": [MAMMINA]})

    # Day 1: the two cinemas write the same film differently; the user votes the first one
    day1 = {
        "andromeda": [show("andromeda", "MAMMINA (1H32')", TODAY)],
        "garden": [show("garden", "mammina (other mommy)", TODAY, 18)],
    }
    await run_sync(db, as_of_date=TODAY, cinemas=CINEMAS, scraper_results=day1)
    assert db.query(Film).count() == 2
    first = db.query(Film).filter_by(normalized_title="mammina").one()
    first.vote = "V"
    db.commit()

    res = await run_sync(db, as_of_date=TODAY, cinemas=CINEMAS, scraper_results=day1, matcher=tmdb)

    film = db.query(Film).one()
    assert film.id == first.id
    assert film.vote == "V"
    assert film.tmdb_id == MAMMINA.id
    assert film.tmdb_match_status == STATUS_MATCHED
    assert film.year == 2026
    assert film.status == "in_sala"
    assert db.query(Showtime).filter_by(film_id=film.id).count() == 2
    snaps = db.query(DailySnapshot).filter_by(sync_date=TODAY).all()
    assert {(s.film_id, s.showtimes_count) for s in snaps} == {(film.id, 1)}
    assert len(snaps) == 2  # one per cinema
    assert db.query(FilmAlias).one().normalized_title == "mammina other mommy"
    assert res.matching.merged_titles == [("mammina (other mommy)", "MAMMINA")]

    # Day 2: the alias sends the Garden title to the merged film, with no new TMDB search
    tmdb.calls.clear()
    day2 = {
        "andromeda": [show("andromeda", "MAMMINA", TODAY + timedelta(days=1))],
        "garden": [show("garden", "mammina (other mommy)", TODAY + timedelta(days=1), 18)],
    }
    res2 = await run_sync(db, as_of_date=TODAY + timedelta(days=1), cinemas=CINEMAS, scraper_results=day2, matcher=tmdb)
    assert db.query(Film).count() == 1
    assert res2.new_films == []
    assert tmdb.calls == []


@pytest.mark.asyncio
async def test_merge_collapses_snapshots_of_the_same_cinema(db):
    tmdb = FakeTmdb({"trainspotting": [TRAINSPOTTING, T2]})
    shows = {
        "garden": [
            show("garden", "TRAINSPOTTING 30° ANNIVERSARIO", TODAY, 18),
            show("garden", "TRAINSPOTTING (RIED.)", TODAY, 21),
        ]
    }
    await run_sync(db, as_of_date=TODAY, cinemas=CINEMAS, scraper_results=shows, matcher=tmdb)

    film = db.query(Film).one()
    assert film.tmdb_id == TRAINSPOTTING.id
    snap = db.query(DailySnapshot).one()
    assert snap.showtimes_count == 2
    # The anniversary screening is an event, the re-release is not: the merged film is not
    assert film.is_event is False


@pytest.mark.asyncio
async def test_review_and_not_found_are_saved(db):
    twin_a = TmdbMovie(1, "Il Ritorno", "The Return", date(2026, 10, 1), 10.0)
    twin_b = TmdbMovie(2, "Il Ritorno", "Il Ritorno", date(2026, 9, 20), 9.5)
    tmdb = FakeTmdb({"il ritorno": [twin_a, twin_b]})
    shows = {"andromeda": [show("andromeda", "IL RITORNO", TODAY), show("andromeda", "FILM FANTASMA", TODAY, 22)]}
    res = await run_sync(db, as_of_date=TODAY, cinemas=CINEMAS, scraper_results=shows, matcher=tmdb)

    ritorno = db.query(Film).filter_by(normalized_title="il ritorno").one()
    fantasma = db.query(Film).filter_by(normalized_title="film fantasma").one()
    assert ritorno.tmdb_match_status == STATUS_REVIEW
    assert ritorno.tmdb_id == twin_a.id  # stored as a suggestion
    assert ritorno.is_tmdb_confirmed is False
    assert fantasma.tmdb_match_status == STATUS_NOT_FOUND
    assert fantasma.tmdb_id is None
    assert [f.raw_title for f in res.matching.to_review] == ["IL RITORNO"]
    assert [f.raw_title for f in res.matching.not_found] == ["FILM FANTASMA"]

    # Neither is searched again tomorrow; "non_trovato" is retried after a week
    tmdb.calls.clear()
    report = await match_pending_films(db, tmdb, today=TODAY + timedelta(days=1))
    assert tmdb.calls == []
    fantasma.tmdb_checked_at = datetime.now(timezone.utc) - timedelta(days=8)
    db.flush()
    report = await match_pending_films(db, tmdb, today=TODAY + timedelta(days=8))
    assert [q for q, _ in tmdb.calls] == ["FILM FANTASMA"]
    assert [f.raw_title for f in report.not_found] == ["FILM FANTASMA"]


@pytest.mark.asyncio
async def test_tmdb_errors_leave_films_pending(db):
    tmdb = FakeTmdb({}, fail=True)
    shows = {"andromeda": [show("andromeda", f"FILM {i}", TODAY, 10 + i) for i in range(5)]}
    res = await run_sync(db, as_of_date=TODAY, cinemas=CINEMAS, scraper_results=shows, matcher=tmdb)

    assert len(tmdb.calls) == 3  # stops after 3 consecutive errors
    assert "interrotto" in res.matching.errors[-1]
    assert all(f.tmdb_match_status is None for f in db.query(Film).all())
    assert res.showtimes == 5  # the sync itself still completes
