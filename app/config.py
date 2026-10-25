"""Application settings – loads .env and config/cinemas.yaml."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import time
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
    AUTO_SYNC_ENABLED: bool = True  # daily sync while the web app is running
    AUTO_SYNC_TIME: time = time(8, 0)
    AUTO_SYNC_CATCHUP_HOURS: int = 20  # at startup, sync if the last good one is older than this
    BACKUPS_DIR: Path = ROOT_DIR / "backups"
    BACKUPS_KEEP: int = 14
    LOGS_DIR: Path = ROOT_DIR / "logs"


def _parse_time(value: str | int) -> time:
    """"HH:MM" from cinemas.yaml or the environment.

    Without quotes YAML reads 20:30 as the number 1230 (minutes in base 60), so
    numbers are converted back. Anything else gives a clear error at startup.
    """
    try:
        if isinstance(value, int) and not isinstance(value, bool):
            return time(value // 60, value % 60)
        hours, minutes = str(value).strip().split(":")
        return time(int(hours), int(minutes))
    except (ValueError, TypeError):
        raise ValueError(
            f'auto_sync_time non valido: {value!r}. Usa il formato "HH:MM", ad esempio "08:00"'
        ) from None


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
        sync_cfg = {}
        s.SYNC_DAYS_TO_USCITO = int(os.getenv("SYNC_DAYS_TO_USCITO", "7"))
        s.SYNC_DAYS_TO_USCITO_EVENTO = int(os.getenv("SYNC_DAYS_TO_USCITO_EVENTO", "3"))

    s.AUTO_SYNC_ENABLED = str(os.getenv("AUTO_SYNC", sync_cfg.get("auto_sync", True))).lower() not in ("0", "false", "no")
    s.AUTO_SYNC_TIME = _parse_time(os.getenv("AUTO_SYNC_TIME", sync_cfg.get("auto_sync_time", "08:00")))
    s.AUTO_SYNC_CATCHUP_HOURS = int(sync_cfg.get("auto_sync_catchup_hours", 20))
    s.BACKUPS_KEEP = int(sync_cfg.get("backups_keep", 14))

    return s



settings = _load_settings()

