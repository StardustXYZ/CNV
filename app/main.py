"""FastAPI application factory."""

from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.db.engine import engine
from app.db.models import Base
from app.web.routes import router


def create_app() -> FastAPI:
    application = FastAPI(title="CineWatch", version="0.1.0")

    # Create tables on first run
    Base.metadata.create_all(bind=engine)

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

