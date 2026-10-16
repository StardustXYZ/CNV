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


@dataclass
class Settings:
    DATABASE_URL: str = ""
    TMDB_API_KEY: str = ""
    CINEMAS: list[CinemaConfig] = field(default_factory=list)


def _load_settings() -> Settings:
    s = Settings()

    # Database – absolute path so it's CWD-independent
    db_path = (ROOT_DIR / "cinewatch.db").as_posix()
    s.DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{db_path}")

    s.TMDB_API_KEY = os.getenv("TMDB_API_KEY", "")

    cinemas_path = ROOT_DIR / "config" / "cinemas.yaml"
    if cinemas_path.exists():
        with open(cinemas_path, encoding="utf-8") as fh:
            data = yaml.safe_load(fh)
        s.CINEMAS = [CinemaConfig(**c) for c in data.get("cinemas", [])]

    return s


settings = _load_settings()

