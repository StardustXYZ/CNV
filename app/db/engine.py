"""SQLAlchemy engine and session factory."""

from sqlalchemy import create_engine
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import sessionmaker

from app.config import settings

# SQLite: wait up to 15 s (default 5 s) when another write is in progress, e.g. a vote
# saved while the sync is writing, instead of failing with "database is locked".
_connect_args = {"timeout": 15} if settings.DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(settings.DATABASE_URL, echo=False, connect_args=_connect_args)
SessionLocal = sessionmaker(bind=engine)


LEGACY_FILM_COLUMNS = (
    "vote", "letterboxd_exported", "exported_at", "in_sala_noticed", "seen_on", "seen_cinema_id", "diary_exported",
)


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
            if "tmdb_match_status" not in columns:
                conn.execute(text("ALTER TABLE films ADD COLUMN tmdb_match_status VARCHAR(20)"))
            if "tmdb_confidence" not in columns:
                conn.execute(text("ALTER TABLE films ADD COLUMN tmdb_confidence FLOAT"))
            if "tmdb_checked_at" not in columns:
                conn.execute(text("ALTER TABLE films ADD COLUMN tmdb_checked_at DATETIME"))
            if "runtime" not in columns:
                conn.execute(text("ALTER TABLE films ADD COLUMN runtime INTEGER"))
            if "genre" not in columns:
                conn.execute(text("ALTER TABLE films ADD COLUMN genre VARCHAR(50)"))
            if "details_tmdb_id" not in columns:
                conn.execute(text("ALTER TABLE films ADD COLUMN details_tmdb_id INTEGER"))
            if "in_sala_pushed" not in columns:
                conn.execute(text("ALTER TABLE films ADD COLUMN in_sala_pushed BOOLEAN DEFAULT 0"))
                # Films already in sala are not news: only the next arrivals are notified
                conn.execute(text("UPDATE films SET in_sala_pushed = 1 WHERE status = 'in_sala'"))
            for name, kind in (
                ("overview", "TEXT"),
                ("director", "VARCHAR(300)"),
                ("cast_names", "VARCHAR(500)"),
                ("credits_tmdb_id", "INTEGER"),
            ):
                if name not in columns:
                    conn.execute(text(f"ALTER TABLE films ADD COLUMN {name} {kind}"))
            if "last_announced_date" not in columns:
                conn.execute(text("ALTER TABLE films ADD COLUMN last_announced_date DATE"))
                # Films announced now: the last time their announcement was read
                conn.execute(
                    text(
                        "UPDATE films SET last_announced_date = "
                        "(SELECT MAX(DATE(c.last_seen)) FROM coming_soon c WHERE c.film_id = films.id)"
                    )
                )
            if "in_theaters" in columns:
                # Written and never read: "status" says it all. It must leave the table too,
                # because it is NOT NULL and new films no longer set it
                conn.execute(text("ALTER TABLE films DROP COLUMN in_theaters"))
            # What the removed local web app kept on each film (votes, Letterboxd export, "seen"
            # details): the Flutter app keeps it in Firestore. The columns must leave the table,
            # because some are NOT NULL and new films no longer set them. One that cannot be
            # dropped (an old table with a foreign key on it) is nullable and just stays unused
            for name in LEGACY_FILM_COLUMNS:
                if name in columns:
                    try:
                        conn.execute(text(f"ALTER TABLE films DROP COLUMN {name}"))
                    except OperationalError:
                        pass

        if "showtimes" in inspector.get_table_names():
            columns = {col["name"] for col in inspector.get_columns("showtimes")}
            if "last_seen" not in columns:
                conn.execute(text("ALTER TABLE showtimes ADD COLUMN last_seen DATETIME"))
                conn.execute(text("UPDATE showtimes SET last_seen = scraped_at WHERE last_seen IS NULL"))
            if "booking_url" not in columns:
                conn.execute(text("ALTER TABLE showtimes ADD COLUMN booking_url VARCHAR(500)"))

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
