"""Logging: a rotating file in logs/cnv.log plus warnings on the console."""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler

from app.config import settings

LOG_FILE_NAME = "cnv.log"
_configured = False


def configure_logging() -> None:
    """Send INFO and above from the app to logs/cnv.log (1 MB × 5 files). Safe to call twice."""
    global _configured
    if _configured:
        return
    settings.LOGS_DIR.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(
        settings.LOGS_DIR / LOG_FILE_NAME, maxBytes=1_000_000, backupCount=5, encoding="utf-8"
    )
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)-7s %(name)s: %(message)s"))
    app_logger = logging.getLogger("app")
    app_logger.setLevel(logging.INFO)
    app_logger.addHandler(handler)
    # httpx logs every request URL, which contains the TMDB api_key
    logging.getLogger("httpx").setLevel(logging.WARNING)
    _configured = True
