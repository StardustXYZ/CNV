"""Tests for the phone version build (data.json + static app)."""

from __future__ import annotations

from datetime import date, datetime, time, timezone
import json

from app.db.models import Cinema, ComingSoon, Film, Showtime
from app.export_static import build_data, build_site

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
    assert data["settings"] == {"days_to_uscito": 7, "days_to_uscito_evento": 3}
    assert "vote" not in json.dumps(data)  # votes stay on the phone


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
