"""Tests for coming-soon ("prossimamente") parsing and sync."""

from __future__ import annotations

from datetime import date, time, timedelta
from pathlib import Path

import pytest

from app.config import CinemaConfig
from app.db.models import Cinema, ComingSoon, Film
from app.scrapers.base import ComingSoonData, ShowtimeData
from app.scrapers.cosenzacinema import parse_home_html, parse_label_date
from app.scrapers.stub import StubScraper
from app.services.sync import ComingSoonBatch, _resolve_cinema, is_placeholder_title, run_sync
from app.services.tmdb import TmdbMovie

FIXTURES = Path(__file__).parent / "fixtures"
TODAY = date(2026, 10, 23)

CINEMAS = [
    CinemaConfig(slug="andromeda-river", name="Andromeda River (Zumpano)", url="https://example.com", scraper="stub"),
    CinemaConfig(slug="citrigno", name="Cinema Citrigno (Cosenza)", url="https://example.com", scraper="stub",
                 aliases=["Cinema Citrigno", "Citrigno"]),
    CinemaConfig(slug="unical", name="Cinema Unical (Rende)", url="https://example.com", scraper="stub",
                 aliases=["Cinema Sale Unical"]),
    CinemaConfig(slug="italia-tieri", name="Cinema Teatro Italia A. Tieri (Cosenza)", url="https://example.com",
                 scraper="stub", aliases=["Cinema Italia/Tieri"]),
]


def item(title: str, cinema: str = "", release: date | None = None, tags: list[str] | None = None) -> ComingSoonData:
    return ComingSoonData(cinema=cinema, raw_title=title, release_date=release, tags=tags or [])


# ------------------------------------------------------------------
# Parsing
# ------------------------------------------------------------------


def test_cosenzacinema_home_lists_events_and_coming_soon_only():
    html = (FIXTURES / "cosenzacinema_home.html").read_text(encoding="utf-8")
    items = {i.raw_title: i for i in parse_home_html(html, reference_date=TODAY)}

    # "In Proiezione" films (already with showtimes on 18tickets) are skipped
    assert "Clayface" not in items and "Primetime" not in items
    assert items["Dracula di Bram Stoker"].cinema == "Cinema Sale Unical"
    assert items["Dracula di Bram Stoker"].release_date == date(2026, 10, 30)
    assert items["Sheep in the Box"].cinema == "Cinema Italia/Tieri"
    assert items["Sheep in the Box"].release_date == date(2026, 10, 27)
    assert items["Ice Cream Man"].cinema == "Cinema Citrigno"
    assert items["Ice Cream Man"].release_date is None
    # A presale start is not a release date
    assert items["Avengers: Doomsday"].release_date is None
    assert set(items) == {
        "Dracula di Bram Stoker", "Sheep in the Box", "RASSEGNA ALTRI SGUARDI",
        "Un Tranquillo Funerale di Famiglia", "Ice Cream Man",
        "Shaun, Vita da Pecora: Operazione Z.U.C.C.A.", "Avengers: Doomsday",
    }


@pytest.mark.parametrize(
    ("label", "expected"),
    [
        ("film evento dal 30 ottobre al 1 novembre - cinema unical", date(2026, 10, 30)),
        ("rassegna altri sguardi - martedi 27 ottobre", date(2026, 10, 27)),
        ("solo il 12 gennaio", date(2027, 1, 12)),
        ("prevendite aperte dal 5 ottobre", None),
        ("VM 18", None),
        ("", None),
    ],
)
def test_parse_label_date(label, expected):
    assert parse_label_date(label, TODAY) == expected


@pytest.mark.parametrize(
    ("title", "placeholder"),
    [
        ("PRIMA VISIONE 2", True),
        ("RASSEGNA ALTRI SGUARDI", True),
        ("#Prima visione 3", True),
        ("  ", True),
        ("DIO RIDE", False),
        ("1917", False),  # a real film
    ],
)
def test_placeholder_titles(title, placeholder):
    assert is_placeholder_title(title) is placeholder


def test_resolve_cinema_by_alias(db):
    cinema_map = {}
    for cfg in CINEMAS:
        c = Cinema(slug=cfg.slug, name=cfg.name, url=cfg.url)
        db.add(c)
        cinema_map[cfg.slug] = c
    assert _resolve_cinema("Cinema Sale Unical", CINEMAS, cinema_map).slug == "unical"
    assert _resolve_cinema("cinema italia/tieri", CINEMAS, cinema_map).slug == "italia-tieri"
    assert _resolve_cinema("citrigno", CINEMAS, cinema_map).slug == "citrigno"
    assert _resolve_cinema("Cinema Inventato", CINEMAS, cinema_map) is None


# ------------------------------------------------------------------
# Sync
# ------------------------------------------------------------------


async def sync(db, day=TODAY, shows=None, coming=None, **kwargs):
    return await run_sync(
        db, as_of_date=day, cinemas=CINEMAS, scraper_results=shows or {}, coming_soon=coming or [], **kwargs
    )


@pytest.mark.asyncio
async def test_sync_saves_announced_films_per_cinema(db):
    andromeda = ComingSoonBatch(
        source="andromeda-river",
        cinema_slug="andromeda-river",
        items=[
            item("IT ENDS (1H30')", release=date(2026, 10, 28)),
            item("SE DOMANI NON TORNO (1H46')", release=date(2026, 11, 5)),
            item("SE DOMANI NON TORNO (1H46')", release=date(2026, 11, 4), tags=["OSPITI IN SALA"]),
            item("PRIMA VISIONE 2", release=date(2026, 12, 1), tags=["ModCineClub"]),
        ],
    )
    cosenza = ComingSoonBatch(
        source="cosenzacinema",
        items=[
            item("Ice Cream Man", "Cinema Citrigno"),
            item("Dracula di Bram Stoker", "Cinema Sale Unical", date(2026, 10, 30)),
            item("RASSEGNA ALTRI SGUARDI", "Cinema Italia/Tieri"),
            item("Film Misterioso", "Cinema Inventato"),
        ],
    )
    res = await sync(db, coming=[andromeda, cosenza])

    titles = {f.raw_title: f for f in db.query(Film).all()}
    assert set(titles) == {"IT ENDS", "SE DOMANI NON TORNO", "Ice Cream Man", "Dracula di Bram Stoker"}
    assert all(f.status == "in_uscita" for f in titles.values())
    se_domani = db.query(ComingSoon).filter_by(film_id=titles["SE DOMANI NON TORNO"].id).one()
    assert se_domani.release_date == date(2026, 11, 4)  # earliest of the two listings
    assert db.query(ComingSoon).filter_by(film_id=titles["Ice Cream Man"].id).one().cinema.slug == "citrigno"
    assert res.coming_soon == {"andromeda-river": 2, "cosenzacinema": 2}
    assert len(res.new_films) == 4


@pytest.mark.asyncio
async def test_sync_drops_announcements_no_longer_listed(db):
    first = ComingSoonBatch("cosenzacinema", [item("Ice Cream Man", "Citrigno"), item("Dracula", "Cinema Sale Unical")])
    await sync(db, coming=[first])
    assert db.query(ComingSoon).count() == 2

    # The source lists only Dracula now
    await sync(db, day=TODAY + timedelta(days=1), coming=[ComingSoonBatch("cosenzacinema", [item("Dracula", "Cinema Sale Unical")])])
    assert [e.film.raw_title for e in db.query(ComingSoon).all()] == ["Dracula"]

    # A source that failed (no batch) keeps what it had
    await sync(db, day=TODAY + timedelta(days=2), coming=[])
    assert db.query(ComingSoon).count() == 1


@pytest.mark.asyncio
async def test_failed_coming_soon_page_is_reported_and_kept(db, monkeypatch):
    await sync(db, coming=[ComingSoonBatch("andromeda-river", [item("IT ENDS")], cinema_slug="andromeda-river")])

    async def broken(self):
        raise RuntimeError("timeout")

    monkeypatch.setattr(StubScraper, "scrape_coming_soon", broken)
    res = await run_sync(db, as_of_date=TODAY, cinemas=CINEMAS[:1], delay_between_cinemas=0)
    assert "andromeda-river (prossimamente)" in res.errors
    assert db.query(ComingSoon).count() == 1


@pytest.mark.asyncio
async def test_announced_film_is_never_marked_uscito(db):
    shows = {"andromeda-river": [ShowtimeData("andromeda-river", "FAST & FURIOUS", TODAY, time(21, 0))]}
    await sync(db, shows=shows)
    film = db.query(Film).one()
    assert film.status == "in_sala"

    # Gone from Andromeda for 10 days, but the Garden-like source announces it again
    later = TODAY + timedelta(days=10)
    other = {"andromeda-river": [ShowtimeData("andromeda-river", "ALTRO", later, time(21, 0))]}
    batch = ComingSoonBatch("citrigno", [item("FAST & FURIOUS")], cinema_slug="citrigno")
    res = await sync(db, day=later, shows=other, coming=[batch])
    db.refresh(film)
    assert film.status == "in_uscita"
    assert film.left_theaters_date is None
    assert any("annunciato di nuovo" in c.details for c in res.status_changes if c.film_id == film.id)


class FakeTmdb:
    def __init__(self, results):
        self.results = results

    async def search_movies(self, query, year=None):
        return self.results.get(query.lower(), [])


@pytest.mark.asyncio
async def test_merge_moves_announcements(db):
    movie = TmdbMovie(1, "Se domani non torno", "Se domani non torno", date(2026, 11, 5), 10.0)
    tmdb = FakeTmdb({"se domani non torno": [movie]})
    batches = [
        ComingSoonBatch("andromeda-river", [item("SE DOMANI NON TORNO (1H46')", release=date(2026, 11, 5))], "andromeda-river"),
        ComingSoonBatch("citrigno", [item("Se Domani Non Torno!")], "citrigno"),
    ]
    await sync(db, coming=batches, matcher=tmdb)

    film = db.query(Film).one()
    assert {e.cinema.slug for e in db.query(ComingSoon).filter_by(film_id=film.id)} == {"andromeda-river", "citrigno"}


def test_label_date_around_new_year():
    assert parse_label_date("film evento dal 30 dicembre", date(2027, 1, 2)) == date(2026, 12, 30)
    assert parse_label_date("solo il 5 gennaio", date(2026, 12, 28)) == date(2027, 1, 5)
