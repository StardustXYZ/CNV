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


MIN_HOURS_BETWEEN_SYNCS = 4  # the daily sync is skipped if a good one ran this recently


def needs_catchup(last_ok_utc: datetime | None, now_utc: datetime, hours: int) -> bool:
    """True when there was never a sync, or the last good one is older than ``hours``."""
    return last_ok_utc is None or now_utc - last_ok_utc > timedelta(hours=hours)


def ran_recently(last_ok_utc: datetime | None, now_utc: datetime, hours: int = MIN_HOURS_BETWEEN_SYNCS) -> bool:
    """True if a good sync ran less than ``hours`` ago (e.g. the catch-up at 07:50)."""
    return last_ok_utc is not None and now_utc - last_ok_utc < timedelta(hours=hours)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class DailySyncScheduler:
    """Runs a sync every day at ``at`` (local time), plus one at startup if data is stale."""

    def __init__(self, session_factory: Callable[[], Session], at: time, catchup_hours: int) -> None:
        self.session_factory = session_factory
        self.at = at
        self.catchup_hours = catchup_hours
        self.next_run: datetime | None = None
        self.running = False

    def _last_ok(self) -> datetime | None:
        with self.session_factory() as db:
            return last_successful_sync(db)

    async def run_forever(self) -> None:
        last = self._last_ok()
        if needs_catchup(last, _utc_now(), self.catchup_hours):
            logger.info("Dati vecchi (ultimo sync: %s): sync di recupero all'avvio", last)
            await self._run()
        while True:
            self.next_run = next_run_after(datetime.now(), self.at)
            await asyncio.sleep(max(0.0, (self.next_run - datetime.now()).total_seconds()))
            await self.run_scheduled()

    async def run_scheduled(self) -> bool:
        """The daily sync, unless a good one just ran (startup catch-up, Sync button...)."""
        last = self._last_ok()
        if ran_recently(last, _utc_now()):
            logger.info("Sync automatico saltato: l'ultimo è di poco fa (%s UTC)", last)
            return False
        await self._run()
        return True

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
