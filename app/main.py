"""FastAPI application factory."""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.db.engine import SessionLocal, init_db
from app.logging_setup import configure_logging
from app.services.scheduler import DailySyncScheduler
from app.web.routes import router


@asynccontextmanager
async def lifespan(application: FastAPI) -> AsyncIterator[None]:
    configure_logging()
    # Create tables and apply schema migrations once at startup
    init_db()

    task = None
    if settings.AUTO_SYNC_ENABLED:
        scheduler = DailySyncScheduler(SessionLocal, settings.AUTO_SYNC_TIME, settings.AUTO_SYNC_CATCHUP_HOURS)
        application.state.scheduler = scheduler
        task = asyncio.create_task(scheduler.run_forever())
    yield
    if task is not None:
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task


def create_app() -> FastAPI:
    application = FastAPI(title="CNV – Chi Ni Vidimu", version="0.1.0", lifespan=lifespan)
    application.state.scheduler = None

    # Static assets
    static_dir = Path(__file__).parent / "web" / "static"
    application.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    # Routes
    application.include_router(router)

    return application


app = create_app()

if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host="127.0.0.1", port=8000, reload=True)
