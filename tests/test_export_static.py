"""Tests for the phone version build (data.json + static app)."""

from __future__ import annotations

from datetime import date, datetime, time, timezone
import json

from app.db.models import Cinema, ComingSoon, Film, FilmMerge, Showtime
import pytest

from app.export_static import build_data, build_site, show_flags

TODAY = date(2026, 10, 30)
NOW = datetime(2026, 10, 30, 11, 0, tzinfo=timezone.utc)


def _seed(db):
    andromeda = Cinema(slug="andromeda", name="Andromeda River", url="https://andromeda.example")
    db.add(andromeda)
    db.flush()
    clay = Film(raw_title="CLAYFACE", normalized_title="clayface", status="in_sala", tmdb_id=1,
                tmdb_title="Clayface", tmdb_match_status="abbinato", poster_url="https://img/clay.jpg", year=2026,
                last_seen_date=TODAY)
    doubt = Film(raw_title="FILM INCERTO", normalized_title="film incerto", status="in_uscita", tmdb_id=2,
                 tmdb_title="Forse questo", tmdb_match_status="da_verificare", poster_url="https://img/x.jpg", year=1990)
    db.add_all([clay, doubt])
    db.flush()
    db.add_all([
        Showtime(film_id=clay.id, cinema_id=andromeda.id, date=TODAY, time=time(21, 0), sala="Sala 1",
                 source_url="https://andromeda.example/film/1", booking_url="https://andromeda.example/buy/1"),
        Showtime(film_id=clay.id, cinema_id=andromeda.id, date=date(2026, 10, 20), time=time(21, 0), sala="Sala 1",
                 source_url="https://andromeda.example/film/1"),  # too old: not exported
        ComingSoon(film_id=doubt.id, cinema_id=andromeda.id, source="andromeda", release_date=None),
    ])
    db.commit()
    return clay, doubt


def test_build_data(db):
    clay, doubt = _seed(db)
    data = build_data(db, today=TODAY, now=NOW)

    assert data["cinemas"] == [{"slug": "andromeda", "name": "Andromeda River", "url": "https://andromeda.example"}]
    assert data["shows"] == [
        {"f": clay.id, "c": "andromeda", "d": "2026-10-30", "t": "21:00", "s": "Sala 1", "u": "https://andromeda.example/buy/1"}
    ]
    assert data["coming"] == [{"f": doubt.id, "c": "andromeda", "d": None}]
    films = {f["id"]: f for f in data["films"]}
    assert films[clay.id]["title"] == "Clayface" and films[clay.id]["tmdb"] == 1
    # An uncertain TMDB match is not shown as if it were sure
    assert films[doubt.id]["title"] == "FILM INCERTO"
    assert films[doubt.id]["tmdb"] is None and films[doubt.id]["poster"] is None
    assert data["settings"] == {"days_to_uscito": 7, "days_to_uscito_evento": 3, "show_extra_minutes": 10}
    assert "vote" not in json.dumps(data)  # votes stay on the phone


def test_build_data_has_the_film_page_on_each_cinema_site(db):
    clay, doubt = _seed(db)
    garden = Cinema(slug="garden", name="Cinema Garden", url="https://garden.example")
    db.add(garden)
    db.flush()
    db.add_all([
        # The shared site's announcement loses to the cinema's own
        ComingSoon(film_id=doubt.id, cinema_id=garden.id, source="cosenzacinema", source_url="https://shared/doubt"),
        ComingSoon(film_id=doubt.id, cinema_id=garden.id, source="garden", source_url="https://garden.example/doubt"),
        # A show's page wins over an announcement, the latest show's over an earlier one
        ComingSoon(film_id=clay.id, cinema_id=garden.id, source="garden", source_url="https://garden.example/soon"),
        Showtime(film_id=clay.id, cinema_id=garden.id, date=TODAY, time=time(18, 0), source_url="https://garden.example/old"),
        Showtime(film_id=clay.id, cinema_id=garden.id, date=date(2026, 11, 2), time=time(18, 0),
                 source_url="https://garden.example/clay"),
    ])
    db.commit()
    data = build_data(db, today=TODAY, now=NOW)
    # The Andromeda announcement of the film in doubt has no page: left out
    assert data["pages"] == [
        {"f": clay.id, "c": "andromeda", "u": "https://andromeda.example/film/1"},
        {"f": clay.id, "c": "garden", "u": "https://garden.example/clay"},
        {"f": doubt.id, "c": "garden", "u": "https://garden.example/doubt"},
    ]


def test_build_data_has_plot_and_credits_only_for_the_confirmed_match(db):
    clay, doubt = _seed(db)
    for f in (clay, doubt):
        f.overview, f.director, f.cast_names, f.credits_tmdb_id = "Trama", "Ada Rossi", "Uno, Due", f.tmdb_id
    db.commit()
    films = {f["id"]: f for f in build_data(db, today=TODAY, now=NOW)["films"]}
    assert (films[clay.id]["plot"], films[clay.id]["director"], films[clay.id]["cast"]) == ("Trama", "Ada Rossi", "Uno, Due")
    assert films[doubt.id]["plot"] is None and films[doubt.id]["cast"] is None


@pytest.mark.parametrize(
    ("tags", "flags"),
    [
        ("V.O. SOTT.", {"vo": True}),
        ("V.O. SOTT.,PRIMA VISIONE", {"vo": True}),
        ("EVENT0 10,V.O.S.,EVENTO 10", {"vo": True}),
        ("Versione originale sottotitolata", {"vo": True}),
        ("14+", {"age": 14}),
        ("14+,EVENTO 8", {"age": 14}),
        ("V.M.18", {"age": 18}),
        ("VM 14", {"age": 14}),
        ("18+,V.O.", {"vo": True, "age": 18}),
        ("EVENTO € 8.00", {}),
        ("PRIMA VISIONE", {}),
        ("VOLUME 2", {}),
        (None, {}),
    ],
)
def test_show_flags(tags, flags):
    assert show_flags(tags) == flags


def test_build_data_marks_original_language_and_age_on_each_show(db):
    clay, _ = _seed(db)
    db.query(Showtime).filter_by(film_id=clay.id, date=TODAY).one().tags = "V.O. SOTT.,14+"
    db.commit()
    show = build_data(db, today=TODAY, now=NOW)["shows"][0]
    assert (show["vo"], show["age"]) == (True, 14)


def test_build_site(db, tmp_path):
    _seed(db)
    data = build_data(db, today=TODAY, now=NOW)
    out = tmp_path / "site"
    build_site(out, data)

    for name in ("index.html", "app.js", "style.css", "phone.css", "manifest.webmanifest", "sw.js",
                 "icons/icon-192.png", "icons/icon-512.png", "data.json"):
        assert (out / name).exists(), name
    assert json.loads((out / "data.json").read_text(encoding="utf-8")) == data
    sw = (out / "sw.js").read_text(encoding="utf-8")
    assert "__BUILD__" not in sw and data["generated_at"] in sw


def test_build_data_lists_merged_films(db):
    clay, doubt = _seed(db)
    db.add_all([
        FilmMerge(old_id=50, new_id=clay.id),       # deleted copy of Clayface
        FilmMerge(old_id=doubt.id, new_id=clay.id),  # id that belongs to a film again: left out
        FilmMerge(old_id=60, new_id=999),            # survivor gone too: nothing to move to
    ])
    db.commit()

    assert build_data(db, today=TODAY, now=NOW)["merged"] == {"50": clay.id}


def test_build_data_runtime_and_genre_only_for_the_confirmed_match(db):
    clay, doubt = _seed(db)
    clay.runtime, clay.genre, clay.details_tmdb_id = 115, "Horror", clay.tmdb_id
    doubt.runtime, doubt.genre, doubt.details_tmdb_id = 90, "Commedia", doubt.tmdb_id  # uncertain match
    db.commit()

    films = {f["id"]: f for f in build_data(db, today=TODAY, now=NOW)["films"]}
    assert (films[clay.id]["runtime"], films[clay.id]["genre"]) == (115, "Horror")
    assert (films[doubt.id]["runtime"], films[doubt.id]["genre"]) == (None, None)


def test_build_data_has_the_first_day_each_film_was_shown(db):
    clay, doubt = _seed(db)
    films = {f["id"]: f for f in build_data(db, today=TODAY, now=NOW)["films"]}
    assert films[clay.id]["since"] == "2026-10-20"  # its oldest show, even if too old to be exported
    assert films[doubt.id]["since"] is None  # only announced


def test_build_data_lists_cinemas_not_updated(db):
    from app.db.models import SyncRun

    _seed(db)
    andromeda = db.query(Cinema).one()
    db.add(SyncRun(sync_date=TODAY, cinema_id=andromeda.id, status="error", created_at=datetime(2026, 10, 30, 2)))
    db.commit()
    assert build_data(db, today=TODAY, now=NOW)["not_updated"] == {"andromeda": None}
