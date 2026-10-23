"""Tests for the web UI (in-memory database, fake TMDB, no lifespan so the real DB is untouched)."""

from __future__ import annotations

from datetime import date, time, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.engine import get_db
from app.db.models import Base, Cinema, Film, FilmAlias, Showtime
from app.main import create_app
from app.services.tmdb import TmdbMovie
from app.web.routes import format_day, format_long_date, get_tmdb

TODAY = date.today()
MAMMINA = TmdbMovie(1400837, "Mammina", "Other Mommy", date(2026, 10, 8), 199.5, "/mammina.jpg")


class FakeTmdb:
    def __init__(self, movies: list[TmdbMovie]) -> None:
        self.movies = {m.id: m for m in movies}

    async def search_movies(self, query: str, year: int | None = None) -> list[TmdbMovie]:
        return [m for m in self.movies.values() if query.lower() in m.title.lower()]

    async def get_movie(self, tmdb_id: int) -> TmdbMovie | None:
        return self.movies.get(tmdb_id)


@pytest.fixture()
def session():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    yield db
    db.close()
    engine.dispose()


@pytest.fixture()
def client(session):
    app = create_app()
    app.dependency_overrides[get_db] = lambda: session
    app.dependency_overrides[get_tmdb] = lambda: FakeTmdb([MAMMINA])
    return TestClient(app)


def add_film(db, title: str, status: str, days: list[int], cinema: Cinema, **fields) -> Film:
    film = Film(raw_title=title, normalized_title=title.lower(), status=status, **fields)
    db.add(film)
    db.flush()
    for offset in days:
        db.add(Showtime(film_id=film.id, cinema_id=cinema.id, date=TODAY + timedelta(days=offset), time=time(21, 0), source_url=""))
    db.commit()
    return film


@pytest.fixture()
def cinema(session):
    c = Cinema(slug="andromeda", name="Andromeda River", url="https://example.com")
    session.add(c)
    session.commit()
    return c


def test_date_formatting():
    ref = date(2026, 10, 23)  # Friday
    assert format_day(ref, ref) == "oggi"
    assert format_day(ref + timedelta(days=1), ref) == "domani"
    assert format_day(date(2026, 10, 26), ref) == "lun 26/10"
    assert format_long_date(date(2026, 12, 16), ref) == "16 dicembre"
    assert format_long_date(date(2027, 1, 2), ref) == "2 gennaio 2027"


def test_home_shows_only_films_in_theaters(client, session, cinema):
    add_film(session, "Clayface", "in_sala", [0, 1], cinema, tmdb_id=1, tmdb_title="Clayface", tmdb_match_status="abbinato")
    add_film(session, "Avengers: Doomsday", "in_uscita", [50], cinema)
    add_film(session, "Vecchio", "uscito", [], cinema)

    html = client.get("/").text
    assert "Clayface" in html
    assert "Avengers" not in html
    assert "Vecchio" not in html
    assert "Andromeda River" in html
    assert "oggi" in html and "21:00" in html
    assert "non è approvato né certificato da TMDB" in html
    assert '<script src="/static/htmx.min.js">' in html


def test_coming_soon_page_sorted_by_first_screening(client, session, cinema):
    add_film(session, "Dune", "in_uscita", [60], cinema)
    add_film(session, "Avengers", "in_uscita", [50], cinema)

    html = client.get("/in-uscita").text
    assert html.index("Avengers") < html.index("Dune")
    assert f"Dal {format_long_date(TODAY + timedelta(days=50))}" in html


def test_vote_toggle_and_filter(client, session, cinema):
    film = add_film(session, "Clayface", "in_sala", [0], cinema)
    add_film(session, "Primetime", "in_sala", [0], cinema)

    resp = client.post(f"/film/{film.id}/vote", data={"v": "V"})
    assert resp.status_code == 200
    assert 'class="btn-vote vote-opt-1 active"' in resp.text
    assert session.get(Film, film.id).vote == "V"

    # Filters
    assert "Primetime" not in client.get("/?voto=V").text
    assert "Clayface" not in client.get("/?voto=nessuno").text

    # Same vote again removes it; empty value too; invalid values are rejected
    client.post(f"/film/{film.id}/vote", data={"v": "V"})
    session.expire_all()
    assert session.get(Film, film.id).vote is None
    client.post(f"/film/{film.id}/vote", data={"v": "X"})
    client.post(f"/film/{film.id}/vote", data={"v": ""})
    session.expire_all()
    assert session.get(Film, film.id).vote is None
    assert client.post(f"/film/{film.id}/vote", data={"v": "Z"}).status_code == 422
    assert client.post("/film/999/vote", data={"v": "V"}).status_code == 404


def test_review_confirm_suggestion_merges_duplicate(client, session, cinema):
    original = add_film(
        session, "MAMMINA", "in_sala", [0], cinema,
        tmdb_id=MAMMINA.id, tmdb_title="Mammina", tmdb_match_status="abbinato", vote="V",
    )
    doubt = add_film(
        session, "mammina (other mommy)", "in_sala", [1], cinema,
        tmdb_id=MAMMINA.id, tmdb_title="Mammina", tmdb_match_status="da_verificare", tmdb_confidence=0.7,
    )

    page = client.get("/da-verificare").text
    assert "mammina (other mommy)" in page
    assert "Sì, è questo" in page

    resp = client.post(f"/film/{doubt.id}/tmdb/conferma", headers={"HX-Request": "true"})
    assert resp.status_code == 200
    assert resp.text == ""  # htmx removes the card

    session.expire_all()
    films = session.query(Film).all()
    assert [f.id for f in films] == [original.id]
    assert films[0].vote == "V"
    assert session.query(Showtime).filter_by(film_id=original.id).count() == 2
    assert session.query(FilmAlias).one().normalized_title == "mammina (other mommy)"
    assert "Tutti i film sono abbinati" in client.get("/da-verificare").text


def test_review_search_and_choose(client, session, cinema):
    film = add_film(session, "MAMMA MIA COSA", "in_sala", [0], cinema, tmdb_match_status="non_trovato")

    partial = client.get(f"/film/{film.id}/tmdb/cerca", params={"q": "mammina"}).text
    assert "Mammina" in partial and "(2026)" in partial
    assert f'"tmdb_id": "{MAMMINA.id}"' in partial
    assert "Nessun risultato" in client.get(f"/film/{film.id}/tmdb/cerca", params={"q": "zzz"}).text

    resp = client.post(f"/film/{film.id}/tmdb/scegli", data={"tmdb_id": MAMMINA.id}, follow_redirects=False)
    assert resp.status_code == 303  # no htmx: back to the review page
    assert resp.headers["location"] == "/da-verificare"
    session.expire_all()
    film = session.get(Film, film.id)
    assert film.tmdb_id == MAMMINA.id
    assert film.tmdb_match_status == "manuale"
    assert film.poster_url.endswith("/mammina.jpg")
    assert client.post(f"/film/{film.id}/tmdb/scegli", data={"tmdb_id": 42}).status_code == 404


def test_nav_counts(client, session, cinema):
    add_film(session, "A", "in_sala", [0], cinema)
    add_film(session, "B", "in_uscita", [9], cinema, tmdb_match_status="da_verificare", tmdb_id=5, tmdb_title="B?")
    add_film(session, "C", "uscito", [], cinema, vote="V")

    html = client.get("/in-uscita").text
    assert '<span class="count count-warn">1</span>' in html
    assert html.count('<span class="count">1</span>') == 3  # in sala, in uscita, watchlist


def test_static_htmx_is_served(client):
    resp = client.get("/static/htmx.min.js")
    assert resp.status_code == 200
    assert "htmx" in resp.text[:2000]
