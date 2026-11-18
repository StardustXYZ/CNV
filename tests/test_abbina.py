"""Tests for the matches chosen by hand (app/abbina.py, app/services/overrides.py); TMDB is faked."""

from __future__ import annotations

import asyncio

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app import abbina
from app.db.models import Base, Film
from app.services.matching import MatchReport
from app.services.overrides import apply_overrides, load_overrides, save_override
from app.services.tmdb import TmdbMovie


class FakeTmdb:
    def __init__(self, *movies: TmdbMovie):
        self.movies = {m.id: m for m in movies}

    async def get_movie(self, tmdb_id):
        return self.movies.get(tmdb_id)


def movie(tmdb_id, title):
    return TmdbMovie(id=tmdb_id, title=title, original_title=title)


def film(db, title, **fields):
    f = Film(raw_title=title, normalized_title=title.lower(), status="in_sala", **fields)
    db.add(f)
    db.flush()
    return f


def test_overrides_file_round_trip(tmp_path):
    path = tmp_path / "abbinamenti.yaml"
    assert load_overrides(path) == {}
    save_override("mammina", 11, path)
    save_override("dune", 22, path)
    save_override("mammina", 33, path)  # a second choice replaces the first
    assert load_overrides(path) == {"dune": 22, "mammina": 33}
    assert path.read_text(encoding="utf-8").startswith("# Abbinamenti a TMDB")


def test_override_gives_the_film_its_match_once(db):
    wrong = film(db, "mammina", tmdb_id=5, tmdb_title="Sbagliato", tmdb_match_status="abbinato")
    other = film(db, "dune", tmdb_id=9, tmdb_match_status="abbinato")
    db.commit()
    tmdb = FakeTmdb(movie(11, "Mammina"))

    assert asyncio.run(apply_overrides(db, tmdb, {"mammina": 11})) == 1
    assert (wrong.tmdb_id, wrong.tmdb_title, wrong.tmdb_match_status) == (11, "Mammina", "manuale")
    assert other.tmdb_id == 9  # films not in the file are not touched
    assert asyncio.run(apply_overrides(db, tmdb, {"mammina": 11})) == 0  # already done


def test_override_to_a_film_that_does_not_exist_on_tmdb_changes_nothing(db):
    f = film(db, "mammina", tmdb_id=5, tmdb_match_status="abbinato")
    db.commit()
    assert asyncio.run(apply_overrides(db, FakeTmdb(), {"mammina": 404})) == 0
    assert f.tmdb_id == 5


def test_override_that_makes_two_films_the_same_merges_them(db):
    old = film(db, "mammina", tmdb_id=11, tmdb_match_status="abbinato")
    new = film(db, "mammina (other mommy)", tmdb_match_status="da_verificare", tmdb_id=7)
    db.commit()
    old_id, new_id = old.id, new.id
    report = MatchReport()
    applied = asyncio.run(apply_overrides(db, FakeTmdb(movie(11, "Mammina")), {"mammina (other mommy)": 11}, report))
    assert applied == 1
    assert report.merges == {new_id: old_id}
    assert db.query(Film).count() == 1


def test_command_line_lists_and_sets_matches(tmp_path, capsys):
    path = tmp_path / "cnv.db"
    engine = create_engine(f"sqlite:///{path.as_posix()}")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        dubious = film(db, "mammina", tmdb_id=5, tmdb_title="Forse", tmdb_match_status="da_verificare")
        film(db, "dune", tmdb_id=9, tmdb_title="Dune", tmdb_match_status="abbinato")
        db.commit()
        dubious_id = dubious.id
    engine.dispose()

    assert abbina.main(["--db", str(path), "lista"]) == 0
    out = capsys.readouterr().out
    assert "mammina" in out and "suggerito: Forse" in out and "dune" not in out

    assert abbina.main(["--db", str(path), "lista", "DUN"]) == 0  # by title, any status
    assert "abbinato: Dune" in capsys.readouterr().out

    saved = tmp_path / "abbinamenti.yaml"
    with Session(create_engine(f"sqlite:///{path.as_posix()}")) as db:
        film_ = abbina.choose(db, dubious_id, 11, saved)
    assert film_.raw_title == "mammina" and load_overrides(saved) == {"mammina": 11}
