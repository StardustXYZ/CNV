"""SQLAlchemy engine and session factory."""

from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import settings

engine = create_engine(settings.DATABASE_URL, echo=False)
SessionLocal = sessionmaker(bind=engine)


def init_db() -> None:
    """Create all database tables if they do not exist and ensure new columns are added."""
    from app.db.models import Base
    from sqlalchemy import inspect, text

    Base.metadata.create_all(bind=engine)

    # Lightweight SQLite schema migration for columns added during development
    with engine.connect() as conn:
        inspector = inspect(conn)

        if "films" in inspector.get_table_names():
            columns = {col["name"] for col in inspector.get_columns("films")}
            if "status" not in columns:
                conn.execute(text("ALTER TABLE films ADD COLUMN status VARCHAR(50) DEFAULT 'in_uscita'"))
            if "left_theaters_date" not in columns:
                conn.execute(text("ALTER TABLE films ADD COLUMN left_theaters_date DATE"))
            if "last_seen_date" not in columns:
                conn.execute(text("ALTER TABLE films ADD COLUMN last_seen_date DATE"))
            if "consecutive_missing_days" not in columns:
                conn.execute(text("ALTER TABLE films ADD COLUMN consecutive_missing_days INTEGER DEFAULT 0"))
            if "is_event" not in columns:
                conn.execute(text("ALTER TABLE films ADD COLUMN is_event BOOLEAN DEFAULT 0"))
            if "letterboxd_exported" not in columns:
                conn.execute(text("ALTER TABLE films ADD COLUMN letterboxd_exported BOOLEAN DEFAULT 0"))

        if "showtimes" in inspector.get_table_names():
            columns = {col["name"] for col in inspector.get_columns("showtimes")}
            if "last_seen" not in columns:
                conn.execute(text("ALTER TABLE showtimes ADD COLUMN last_seen DATETIME"))
                conn.execute(text("UPDATE showtimes SET last_seen = scraped_at WHERE last_seen IS NULL"))

        if "daily_snapshots" in inspector.get_table_names():
            # Deduplicate any potential duplicates keeping the one with max id
            conn.execute(text("""
                DELETE FROM daily_snapshots
                WHERE id NOT IN (
                    SELECT MAX(id)
                    FROM daily_snapshots
                    GROUP BY sync_date, cinema_id, film_id
                )
            """))
            conn.execute(text("""
                CREATE UNIQUE INDEX IF NOT EXISTS uq_daily_snapshots_date_cinema_film
                ON daily_snapshots(sync_date, cinema_id, film_id)
            """))

        conn.commit()


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency – yields a DB session and closes it after the request."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


