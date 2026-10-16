"""Tests for the Letterboxd export service."""

from __future__ import annotations

from datetime import datetime, timezone

from app.db.models import Film
from app.services.export import export_letterboxd_csv


def test_export_empty_db(db):
    csv = export_letterboxd_csv(db)
    lines = csv.strip().splitlines()
    assert lines[0] == "Title,Year"
    assert len(lines) == 1  # header only


def test_export_includes_eligible_films(db):
    film = Film(
        raw_title="Film da Vedere",
        normalized_title="film da vedere",
        in_theaters=False,
        vote="V",
        first_seen=datetime.now(timezone.utc),
        last_seen=datetime.now(timezone.utc),
    )
    db.add(film)
    db.commit()

    csv = export_letterboxd_csv(db)
    assert "Film da Vedere" in csv


def test_export_excludes_in_theater_films(db):
    film = Film(
        raw_title="Ancora al Cinema",
        normalized_title="ancora al cinema",
        in_theaters=True,
        vote="V",
        first_seen=datetime.now(timezone.utc),
        last_seen=datetime.now(timezone.utc),
    )
    db.add(film)
    db.commit()

    csv = export_letterboxd_csv(db)
    assert "Ancora al Cinema" not in csv


def test_export_excludes_x_votes(db):
    film = Film(
        raw_title="Non Mi Interessa",
        normalized_title="non mi interessa",
        in_theaters=False,
        vote="X",
        first_seen=datetime.now(timezone.utc),
        last_seen=datetime.now(timezone.utc),
    )
    db.add(film)
    db.commit()

    csv = export_letterboxd_csv(db)
    assert "Non Mi Interessa" not in csv

