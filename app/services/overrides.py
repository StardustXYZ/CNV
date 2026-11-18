"""Matches to TMDB chosen by hand, kept in config/abbinamenti.yaml.

The database that feeds the app lives on GitHub (branch "dati") and is rebuilt every night,
so a correction made on the PC cannot be saved in it. It is saved here instead, in a file of
the project: the nightly sync reads it and applies each correction once (title -> TMDB id).
The file is edited with ``python -m app.abbina``.
"""

from __future__ import annotations

import logging
from pathlib import Path

import httpx
from sqlalchemy.orm import Session
import yaml

from app.config import ROOT_DIR
from app.db.models import Film
from app.services.matching import STATUS_MANUAL, MatchReport, confirm_match

logger = logging.getLogger(__name__)

OVERRIDES_PATH = ROOT_DIR / "config" / "abbinamenti.yaml"

HEADER = """\
# Abbinamenti a TMDB scelti a mano: titolo normalizzato del film -> id TMDB.
# Si modifica con `python -m app.abbina`; il sync notturno li applica una volta sola.
"""


def load_overrides(path: Path = OVERRIDES_PATH) -> dict[str, int]:
    if not path.exists():
        return {}
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return {str(title): int(tmdb_id) for title, tmdb_id in (data.get("abbinamenti") or {}).items()}


def save_override(normalized_title: str, tmdb_id: int, path: Path = OVERRIDES_PATH) -> None:
    overrides = load_overrides(path)
    overrides[normalized_title] = int(tmdb_id)
    body = yaml.safe_dump({"abbinamenti": overrides}, allow_unicode=True, sort_keys=True, default_flow_style=False)
    path.write_text(HEADER + body, encoding="utf-8")


async def apply_overrides(
    db: Session, tmdb, overrides: dict[str, int] | None = None, report: MatchReport | None = None
) -> int:
    """Give each film listed in the file the TMDB match chosen by hand. Returns how many changed.

    A film already matched by hand to that id is left alone. Duplicates that become the same
    film are merged, and recorded in ``report.merges`` like the automatic matching does.
    """
    overrides = load_overrides() if overrides is None else overrides
    if not overrides or not hasattr(tmdb, "get_movie"):
        return 0
    applied = 0
    films = db.query(Film).filter(Film.normalized_title.in_(overrides)).all()
    for film in films:
        wanted = overrides[film.normalized_title]
        if film.tmdb_id == wanted and film.tmdb_match_status == STATUS_MANUAL:
            continue
        title = film.raw_title
        try:
            movie = await tmdb.get_movie(wanted)
            if movie is None:
                logger.warning("Abbinamento a mano di %s: il film TMDB %s non esiste", title, wanted)
                continue
            before = {row[0] for row in db.query(Film.id)}
            survivor = confirm_match(db, film, movie)
            db.commit()
        except httpx.HTTPError as err:
            db.rollback()
            logger.warning("Abbinamento a mano di %s non riuscito: %s", title, err.__class__.__name__)
            continue
        applied += 1
        if report is not None:
            for gone in before - {row[0] for row in db.query(Film.id)}:
                report.merges[gone] = survivor.id
                report.merged_titles.append((title, survivor.raw_title))
    return applied
