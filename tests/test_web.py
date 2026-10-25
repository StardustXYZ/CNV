"""Tests for the web UI (in-memory database, fake TMDB, no lifespan so the real DB is untouched)."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.engine import get_db
from app.db.models import Base, Cinema, Film, FilmAlias, Showtime
from app.main import create_app
from app.web import routes
from app.services.tmdb import TmdbMovie
from app.web.routes import format_day, format_long_date, get_tmdb, programme_day, show_datetime

TODAY = date(2026, 10, 17)
NOW = datetime(2026, 10, 17, 20, 0)  # Saturday 17/10, 20:00
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
def client(session, monkeypatch):
    monkeypatch.setattr(routes, "_now", lambda: NOW)
    app = create_app()
    app.dependency_overrides[get_db] = lambda: session
    app.dependency_overrides[get_tmdb] = lambda: FakeTmdb([MAMMINA])
    return TestClient(app)


def add_film(db, title: str, status: str, days: list[int], cinema: Cinema, **fields) -> Film:
    film = Film(raw_title=title, normalized_title=title.lower(), status=status, **fields)
    db.add(film)
    db.flush()
    for offset in days:
        add_show(db, film, cinema, TODAY + timedelta(days=offset), time(21, 0))
    db.commit()
    return film


def add_show(db, film: Film, cinema: Cinema, day: date, at: time, sala: str | None = "Sala 1") -> None:
    db.add(Showtime(film_id=film.id, cinema_id=cinema.id, date=day, time=at, sala=sala, source_url=""))
    db.commit()


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
    assert 'data-show-at="2026-10-17T21:00"' in html
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


# ------------------------------------------------------------------
# Today's screenings and coming-soon cinemas
# ------------------------------------------------------------------


def test_programme_day_and_late_shows():
    assert programme_day(datetime(2026, 10, 17, 20, 0)) == date(2026, 10, 17)
    # At 00:30 the evening programme of the 17th is still running
    assert programme_day(datetime(2026, 10, 18, 0, 30)) == date(2026, 10, 17)
    assert programme_day(datetime(2026, 10, 18, 6, 0)) == date(2026, 10, 18)
    # A 00:00 show listed under the 17th starts at midnight between the 17th and the 18th
    assert show_datetime(date(2026, 10, 17), time(0, 0)) == datetime(2026, 10, 18, 0, 0)
    assert show_datetime(date(2026, 10, 17), time(21, 0)) == datetime(2026, 10, 17, 21, 0)


def test_home_shows_only_remaining_shows_of_today_by_cinema_and_sala(client, session, cinema):
    garden = Cinema(slug="garden", name="Cinema Garden (Rende)", url="https://example.com")
    session.add(garden)
    session.commit()
    film = add_film(session, "Clayface", "in_sala", [], cinema)
    # It is 20:00 on 17/10: 19:00 has started, 21:00 and 00:00 (after midnight) are still ahead
    add_show(session, film, cinema, TODAY, time(19, 0), "Sala 1")
    add_show(session, film, cinema, TODAY, time(21, 0), "Sala 1")
    add_show(session, film, cinema, TODAY, time(0, 0), "Sala 1")
    add_show(session, film, cinema, TODAY, time(22, 30), "Sala 3")
    add_show(session, film, garden, TODAY, time(20, 30), "Sala A")
    # Other days never appear
    add_show(session, film, cinema, TODAY + timedelta(days=1), time(17, 0), "Sala 1")
    add_show(session, film, cinema, TODAY - timedelta(days=1), time(21, 0), "Sala 1")

    html = client.get("/").text
    shows = [s.split('"')[0] for s in html.split('data-show-at="')[1:]]
    assert shows == [
        "2026-10-17T20:30",  # Garden first: its first show is the earliest
        "2026-10-17T21:00",
        "2026-10-18T00:00",
        "2026-10-17T22:30",
    ]
    assert html.index("Cinema Garden (Rende)") < html.index("Andromeda River")
    assert html.index("Sala 1") < html.index("Sala 3")
    assert ">00:00<" in html
    assert "19:00" not in html and "17:00" not in html


def test_home_after_midnight_keeps_the_evening_programme(client, session, cinema, monkeypatch):
    monkeypatch.setattr(routes, "_now", lambda: datetime(2026, 10, 18, 0, 30))
    film = add_film(session, "Clayface", "in_sala", [], cinema)
    add_show(session, film, cinema, TODAY, time(0, 0))  # started at 00:00
    add_show(session, film, cinema, TODAY, time(1, 15))  # still to come tonight
    add_show(session, film, cinema, TODAY + timedelta(days=1), time(16, 0))  # tomorrow afternoon

    html = client.get("/").text
    assert [s.split('"')[0] for s in html.split('data-show-at="')[1:]] == ["2026-10-18T01:15"]


def test_home_lists_films_still_showing_today_first(client, session, cinema):
    add_film(session, "Aaa finito per oggi", "in_sala", [1], cinema)  # only tomorrow
    add_film(session, "Zzz stasera", "in_sala", [0], cinema)  # 21:00 today

    html = client.get("/").text
    assert html.index("Zzz stasera") < html.index("Aaa finito per oggi")
    assert "Oggi non ci sono altri spettacoli." in html


def test_coming_soon_lists_cinemas_with_their_dates(client, session, cinema):
    unical = Cinema(slug="unical", name="Cinema Unical (Rende)", url="https://example.com")
    session.add(unical)
    session.commit()
    film = add_film(session, "Avengers", "in_uscita", [], cinema)
    add_show(session, film, cinema, date(2026, 12, 16), time(20, 30))
    add_show(session, film, unical, date(2026, 12, 16), time(21, 0))
    add_show(session, film, unical, date(2026, 12, 17), time(21, 0))
    add_film(session, "Matrix", "in_uscita", [], cinema)
    add_show(session, session.query(Film).filter_by(raw_title="Matrix").one(), cinema, date(2026, 10, 26), time(19, 15))
    late = Cinema(slug="garden", name="Cinema Garden (Rende)", url="https://example.com")
    session.add(late)
    session.commit()
    add_show(session, film, late, date(2026, 12, 20), time(18, 0))

    html = client.get("/in-uscita").text
    assert html.index("Matrix") < html.index("Avengers")
    avengers = html[html.index("Avengers"):]
    assert "Dal 16 dicembre" in html
    assert avengers.index("Andromeda River") < avengers.index("Cinema Unical (Rende)") < avengers.index("Cinema Garden (Rende)")
    assert "dal 20 dicembre" in avengers  # only the cinema starting later shows its own date
    assert avengers.count("dal 16 dicembre") == 0
    assert 'data-show-at="' not in html  # no times on the coming-soon page


def test_home_separates_films_no_longer_programmed(client, session, cinema):
    add_film(session, "Clayface", "in_sala", [0, 1], cinema)
    frankie = add_film(session, "Frankie", "in_sala", [-5, -4], cinema)
    frankie.last_seen_date = TODAY - timedelta(days=5)
    session.commit()

    html = client.get("/").text
    grid = html[: html.index("gone-section")]
    gone = html[html.index("gone-section"):]
    assert "Clayface" in grid and "Frankie" not in grid
    assert "Frankie" in gone
    assert "uscito dalle sale dal 19 ottobre se non ricompare" in gone  # 12/10 + 7 days
    assert '<span class="count">1</span>' in html  # nav: only Clayface is in sala


def test_coming_soon_page_lists_announced_films(client, session, cinema):
    from app.db.models import ComingSoon

    garden = Cinema(slug="garden", name="Cinema Garden (Rende)", url="https://example.com")
    session.add(garden)
    session.commit()
    dio_ride = add_film(session, "DIO RIDE", "in_uscita", [], cinema)
    it_ends = add_film(session, "IT ENDS", "in_uscita", [], cinema)
    session.add_all([
        ComingSoon(film_id=dio_ride.id, cinema_id=garden.id, source="garden"),
        ComingSoon(film_id=it_ends.id, cinema_id=cinema.id, source="andromeda-river", release_date=date(2026, 10, 28)),
    ])
    add_film(session, "Orfano", "in_uscita", [], cinema)  # no shows, no announcement: hidden
    clayface = add_film(session, "Clayface", "in_sala", [0], cinema)
    session.add(ComingSoon(film_id=clayface.id, cinema_id=garden.id, source="garden"))
    session.commit()

    html = client.get("/in-uscita").text
    assert html.index("IT ENDS") < html.index("DIO RIDE")  # dated first
    assert "Dal 28 ottobre" in html
    assert "Data da definire" in html and "data da definire" in html
    assert "Orfano" not in html and "Clayface" not in html

    home = client.get("/").text
    assert "In arrivo anche: Cinema Garden (Rende)" in home


def test_watchlist_export_flow(client, session, cinema):
    ready = add_film(session, "Frankie", "uscito", [], cinema, vote="V", tmdb_id=10,
                     tmdb_title="Frankie e le creature dimenticate", tmdb_match_status="abbinato", year=2026)
    add_film(session, "Incerto", "uscito", [], cinema, vote="?", tmdb_id=11, tmdb_match_status="da_verificare")
    add_film(session, "Non mi va", "uscito", [], cinema, vote="X", tmdb_id=12, tmdb_match_status="abbinato")

    page = client.get("/watchlist").text
    assert "Da esportare" in page and "Frankie e le creature dimenticate" in page
    assert "1 film senza abbinamento TMDB" in page and "Incerto" in page
    assert "Non mi va" not in page

    resp = client.get("/export")
    assert resp.headers["content-disposition"] == "attachment; filename=letterboxd_watchlist_2026-10-17.csv"
    assert resp.text.splitlines() == ["tmdbID,Title,Year", "10,Frankie e le creature dimenticate,2026"]

    resp = client.post("/watchlist/esportati", data={"film_ids": [ready.id]}, follow_redirects=False)
    assert resp.status_code == 303
    page = client.get("/watchlist").text
    assert "Già esportati" in page and "Esporta di nuovo" in page
    assert client.get("/export").text.splitlines() == ["tmdbID,Title,Year"]

    client.post(f"/film/{ready.id}/esporta-di-nuovo")
    assert len(client.get("/export").text.splitlines()) == 2


def test_status_page(client, session, cinema):
    from app.db.models import SyncLog, SyncRun

    session.add(SyncRun(sync_date=TODAY, cinema_id=cinema.id, status="ok", showtimes_count=42))
    session.add(SyncLog(trigger="automatico", ok=True, started_at=datetime(2026, 10, 17, 6, 0),
                        finished_at=datetime(2026, 10, 17, 6, 2), showtimes=180, new_films=3,
                        errors="garden (prossimamente): timeout"))
    session.commit()

    html = client.get("/stato").text
    assert "Andromeda River" in html and ">42<" in html
    assert "automatico" in html and "con errori" in html
    assert "garden (prossimamente): timeout" in html
    assert "Backup del database" in html
    assert "C'era già un sync in corso" not in html
    assert "C'era già un sync in corso" in client.get("/stato?occupato=1").text


def test_favicon_is_served(client):
    resp = client.get("/favicon.ico")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "image/x-icon"
    assert resp.content[:4] == b"\x00\x00\x01\x00"  # ICO header


def test_launcher_detects_a_running_server():
    import socket

    from app.launcher import is_running

    with socket.socket() as server:
        server.bind(("127.0.0.1", 0))
        server.listen()
        port = server.getsockname()[1]
        assert is_running(port=port)
    assert not is_running(port=port)


# ------------------------------------------------------------------
# Change TMDB match, watchlist count, other websites
# ------------------------------------------------------------------


def test_change_match_page_and_redirect_back(client, session, cinema):
    film = add_film(session, "MAMMINA", "in_uscita", [3], cinema,
                    tmdb_id=15660, tmdb_title="Mammina cara", tmdb_match_status="abbinato", year=1981)

    assert f'href="/film/{film.id}/abbinamento"' in client.get("/in-uscita").text

    page = client.get(f"/film/{film.id}/abbinamento", headers={"referer": "http://testserver/in-uscita"}).text
    assert "Mammina cara" in page and "Abbinato in automatico" in page
    assert 'name="dopo" value="/in-uscita"' in page

    partial = client.get(f"/film/{film.id}/tmdb/cerca", params={"q": "mammina", "dopo": "/in-uscita"}).text
    assert "&#34;dopo&#34;: &#34;/in-uscita&#34;" in partial or '"dopo": "/in-uscita"' in partial

    resp = client.post(
        f"/film/{film.id}/tmdb/scegli",
        data={"tmdb_id": MAMMINA.id, "dopo": "/in-uscita"},
        headers={"HX-Request": "true"},
    )
    assert resp.headers["HX-Redirect"] == "/in-uscita"
    session.expire_all()
    film = session.get(Film, film.id)
    assert (film.tmdb_id, film.tmdb_match_status, film.year) == (MAMMINA.id, "manuale", 2026)


def test_change_match_never_redirects_to_another_site(client, session, cinema):
    film = add_film(session, "MAMMINA", "in_uscita", [3], cinema)
    resp = client.post(
        f"/film/{film.id}/tmdb/scegli",
        data={"tmdb_id": MAMMINA.id, "dopo": "https://evil.example/"},
        follow_redirects=False,
    )
    assert resp.headers["location"] == "/da-verificare"
    page = client.get(f"/film/{film.id}/abbinamento", headers={"referer": "https://evil.example/x"}).text
    assert 'name="dopo" value="/"' in page


def test_watchlist_count_ignores_films_already_exported(client, session, cinema):
    add_film(session, "Da esportare", "uscito", [], cinema, vote="V")
    add_film(session, "Esportato", "uscito", [], cinema, vote="V", letterboxd_exported=True)
    html = client.get("/stato").text
    assert 'href="/watchlist" class="">\n                Watchlist\n                <span class="count">1</span>' in html


def test_actions_from_other_websites_are_blocked(client, session, cinema):
    film = add_film(session, "Clayface", "in_sala", [0], cinema)
    evil = client.post(f"/film/{film.id}/vote", data={"v": "V"}, headers={"origin": "https://evil.example"})
    assert evil.status_code == 403
    assert client.post("/sync", headers={"origin": "https://evil.example"}).status_code == 403
    session.expire_all()
    assert session.get(Film, film.id).vote is None

    ok = client.post(f"/film/{film.id}/vote", data={"v": "V"}, headers={"origin": "http://testserver"})
    assert ok.status_code == 200
