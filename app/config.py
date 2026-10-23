"""Application settings – loads .env and config/cinemas.yaml."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml
from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parent.parent

load_dotenv(ROOT_DIR / ".env")


@dataclass
class CinemaConfig:
    slug: str
    name: str
    url: str
    scraper: str
    aliases: list[str] = field(default_factory=list)  # names used by other sites, e.g. "Cinema Sale Unical"


@dataclass
class ComingSoonSourceConfig:
    """A site listing upcoming films for several cinemas (each card names its cinema)."""

    slug: str
    name: str
    url: str
    scraper: str


@dataclass
class Settings:
    DATABASE_URL: str = ""
    TMDB_API_KEY: str = ""
    CINEMAS: list[CinemaConfig] = field(default_factory=list)
    COMING_SOON_SOURCES: list[ComingSoonSourceConfig] = field(default_factory=list)
    SYNC_DAYS_TO_USCITO: int = 7
    SYNC_DAYS_TO_USCITO_EVENTO: int = 3


def _load_settings() -> Settings:
    s = Settings()

    # Database – absolute path so it's CWD-independent
    db_path = (ROOT_DIR / "cinewatch.db").as_posix()
    s.DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{db_path}")

    s.TMDB_API_KEY = os.getenv("TMDB_API_KEY", "")

    cinemas_path = ROOT_DIR / "config" / "cinemas.yaml"
    if cinemas_path.exists():
        with open(cinemas_path, encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}
        s.CINEMAS = [CinemaConfig(**c) for c in data.get("cinemas", [])]
        s.COMING_SOON_SOURCES = [ComingSoonSourceConfig(**c) for c in data.get("coming_soon_sources", [])]
        sync_cfg = data.get("sync_settings", {})
        s.SYNC_DAYS_TO_USCITO = int(os.getenv("SYNC_DAYS_TO_USCITO", str(sync_cfg.get("days_to_uscito", 7))))
        s.SYNC_DAYS_TO_USCITO_EVENTO = int(
            os.getenv("SYNC_DAYS_TO_USCITO_EVENTO", str(sync_cfg.get("days_to_uscito_evento", 3)))
        )
    else:
        s.SYNC_DAYS_TO_USCITO = int(os.getenv("SYNC_DAYS_TO_USCITO", "7"))
        s.SYNC_DAYS_TO_USCITO_EVENTO = int(os.getenv("SYNC_DAYS_TO_USCITO_EVENTO", "3"))

    return s



settings = _load_settings()

