"""Tests for the Letterboxd export service."""

from __future__ import annotations

import csv
import io

from app.db.models import Film
from app.services.export import (
    export_letterboxd_csv,
    exportable_films,
    exported_films,
    films_missing_tmdb,
    mark_exported,
    unmark_exported,
)


def add(db, title: str, status: str = "uscito", vote: str | None = "V", tmdb_id: int | None = 1, match="abbinato", **kw) -> Film:
    film = Film(
        raw_title=title,
        normalized_title=title.lower(),
        status=status,
        vote=vote,
        tmdb_id=tmdb_id,
        tmdb_title=f"{title} (TMDB)" if tmdb_id else None,
        tmdb_match_status=match if tmdb_id else None,
        year=2026 if tmdb_id else None,
        **kw,
    )
    db.add(film)
    db.commit()
    return film


def rows(text: str) -> list[dict[str, str]]:
    return list(csv.DictReader(io.StringIO(text)))


def test_export_empty_db(db):
    assert export_letterboxd_csv(db).splitlines() == ["tmdbID,Title,Year"]


def test_export_includes_left_films_marked_v_or_question(db):
    add(db, "Da Vedere", vote="V", tmdb_id=101)
    add(db, "Forse", vote="?", tmdb_id=102)
    add(db, "No", vote="X", tmdb_id=103)
    add(db, "Senza Voto", vote=None, tmdb_id=104)
    add(db, "Ancora In Sala", status="in_sala", tmdb_id=105)
    add(db, "Prossimamente", status="in_uscita", tmdb_id=106)

    assert rows(export_letterboxd_csv(db)) == [
        {"tmdbID": "101", "Title": "Da Vedere (TMDB)", "Year": "2026"},
        {"tmdbID": "102", "Title": "Forse (TMDB)", "Year": "2026"},
    ]


def test_export_skips_films_without_confirmed_tmdb(db):
    add(db, "Confermato", tmdb_id=1, match="manuale")
    add(db, "Incerto", tmdb_id=2, match="da_verificare")
    add(db, "Sconosciuto", tmdb_id=None)

    assert [r["tmdbID"] for r in rows(export_letterboxd_csv(db))] == ["1"]
    assert sorted(f.raw_title for f in films_missing_tmdb(db)) == ["Incerto", "Sconosciuto"]


def test_mark_and_unmark_exported(db):
    a = add(db, "A", tmdb_id=1)
    b = add(db, "B", tmdb_id=2)

    # Downloading does not mark anything
    export_letterboxd_csv(db)
    assert len(exportable_films(db)) == 2

    assert mark_exported(db, [a.id]) == 1
    assert mark_exported(db, [a.id]) == 0  # already exported
    db.commit()
    assert [f.id for f in exportable_films(db)] == [b.id]
    assert [f.id for f in exported_films(db)] == [a.id]
    assert a.exported_at is not None
    assert "A (TMDB)" not in export_letterboxd_csv(db)

    unmark_exported(db, a)
    db.commit()
    assert {f.id for f in exportable_films(db)} == {a.id, b.id}

