"""Daily automatic sync while the web app is running."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from datetime import datetime, time, timedelta, timezone
import logging

from sqlalchemy.orm import Session

from app.services.runner import SyncAlreadyRunning, last_successful_sync, run_full_sync

logger = logging.getLogger(__name__)


def next_run_after(now: datetime, at: time) -> datetime:
    """Next local time ``at`` strictly after ``now``."""
    candidate = datetime.combine(now.date(), at)
    return candidate if candidate > now else candidate + timedelta(days=1)


def needs_catchup(last_ok_utc: datetime | None, now_utc: datetime, hours: int) -> bool:
    """True when there was never a sync, or the last good one is older than ``hours``."""
    return last_ok_utc is None or now_utc - last_ok_utc > timedelta(hours=hours)


class DailySyncScheduler:
    """Runs a sync every day at ``at`` (local time), plus one at startup if data is stale."""

    def __init__(self, session_factory: Callable[[], Session], at: time, catchup_hours: int) -> None:
        self.session_factory = session_factory
        self.at = at
        self.catchup_hours = catchup_hours
        self.next_run: datetime | None = None
        self.running = False

    async def run_forever(self) -> None:
        with self.session_factory() as db:
            last = last_successful_sync(db)
        if needs_catchup(last, datetime.now(timezone.utc).replace(tzinfo=None), self.catchup_hours):
            logger.info("Dati vecchi (ultimo sync: %s): sync di recupero all'avvio", last)
            await self._run()
        while True:
            self.next_run = next_run_after(datetime.now(), self.at)
            await asyncio.sleep(max(0.0, (self.next_run - datetime.now()).total_seconds()))
            await self._run()

    async def _run(self) -> None:
        self.running = True
        try:
            with self.session_factory() as db:
                await run_full_sync(db, "automatico")
        except SyncAlreadyRunning:
            logger.info("Sync automatico saltato: un altro sync è in corso")
        except Exception:
            logger.exception("Sync automatico non riuscito")
        finally:
            self.running = False
