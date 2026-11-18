"""The sync must not keep the database locked while it waits on websites or TMDB.

Uses a real SQLite file: the lock cannot be seen with an in-memory database.
"""

from __future__ import annotations

from datetime import date, time

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.config import CinemaConfig
from app.db.models import Base, Film
from app.scrapers.base import BaseScraper, ShowtimeData
from app.services import sync as sync_module
from app.services.sync import run_sync
from app.services.tmdb import TmdbMovie

TODAY = date(2026, 10, 23)


@pytest.fixture()
def db_file(tmp_path):
    path = tmp_path / "cnv.db"
    engine = create_engine(f"sqlite:///{path.as_posix()}")
    Base.metadata.create_all(engine)
    with sessionmaker(bind=engine)() as s:
        s.add(Film(raw_title="FILM SCRITTO", normalized_title="film scritto", status="in_sala"))
        s.commit()
    yield path, engine
    engine.dispose()


def write_from_another_process(path, outcomes: list[str]) -> None:
    """A write from another connection with a short wait (what the phone-side tools or a second process do)."""
    engine = create_engine(f"sqlite:///{path.as_posix()}", connect_args={"timeout": 1})
    try:
        with sessionmaker(bind=engine)() as s:
            film = s.query(Film).filter_by(normalized_title="film scritto").one()
            film.in_sala_pushed = not film.in_sala_pushed
            s.commit()
        outcomes.append("ok")
    except Exception as err:  # noqa: BLE001 - recorded, asserted below
        outcomes.append(f"{type(err).__name__}: {err}")
    finally:
        engine.dispose()


@pytest.mark.asyncio
async def test_writes_are_saved_while_the_sync_reads_websites_and_tmdb(db_file, monkeypatch):
    path, engine = db_file
    outcomes: list[str] = []

    class SlowWebsite(BaseScraper):
        async def scrape(self):
            write_from_another_process(path, outcomes)  # another process writes while we wait on the site
            return [ShowtimeData(self.cinema_slug, f"FILM {self.cinema_slug.upper()}", TODAY, time(21, 0))]

    class SlowTmdb:
        async def search_movies(self, query, year=None):
            write_from_another_process(path, outcomes)  # ...and while we wait on TMDB
            return [TmdbMovie(abs(hash(query)) % 10_000, query.title(), query.title(), TODAY, 1.0)]

    monkeypatch.setitem(sync_module.SCRAPER_REGISTRY, "slow", SlowWebsite)
    cinemas = [
        CinemaConfig(slug="uno", name="Uno", url="https://example.com", scraper="slow"),
        CinemaConfig(slug="due", name="Due", url="https://example.com", scraper="slow"),
    ]
    with sessionmaker(bind=engine)() as db:
        res = await run_sync(
            db, as_of_date=TODAY, cinemas=cinemas, coming_soon=[], delay_between_cinemas=0, matcher=SlowTmdb()
        )

    assert res.errors == {}
    assert res.showtimes == 2
    assert len(outcomes) >= 4  # 2 websites + TMDB searches
    assert outcomes == ["ok"] * len(outcomes)
