"""ORM models – Cinema, Film, FilmAlias, FilmMerge, ComingSoon, Showtime, DailySnapshot, SyncRun, SyncLog."""

from __future__ import annotations

from datetime import date, datetime, time, timezone

from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, Integer, String, Text, Time, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class Cinema(Base):
    __tablename__ = "cinemas"

    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(200))
    url: Mapped[str] = mapped_column(String(500))

    showtimes: Mapped[list[Showtime]] = relationship(back_populates="cinema")
    snapshots: Mapped[list[DailySnapshot]] = relationship(back_populates="cinema")

    def __repr__(self) -> str:
        return f"<Cinema {self.slug!r}>"


class Film(Base):
    __tablename__ = "films"

    id: Mapped[int] = mapped_column(primary_key=True)
    raw_title: Mapped[str] = mapped_column(String(300))  # Titolo pulito
    normalized_title: Mapped[str] = mapped_column(String(300), index=True)
    tmdb_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    tmdb_title: Mapped[str | None] = mapped_column(String(300), nullable=True)
    # None (da cercare) | abbinato | da_verificare | non_trovato | manuale
    # With "da_verificare" the tmdb_* fields hold the best suggestion, not a confirmed match.
    tmdb_match_status: Mapped[str | None] = mapped_column(String(20), nullable=True, index=True)
    tmdb_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    tmdb_checked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    poster_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    year: Mapped[int | None] = mapped_column(Integer, nullable=True)  # Anno
    status: Mapped[str] = mapped_column(String(50), default="in_uscita", index=True)  # in_uscita | in_sala | uscito
    left_theaters_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    first_seen: Mapped[datetime] = mapped_column(DateTime, default=_utc_now)
    last_seen: Mapped[datetime] = mapped_column(DateTime, default=_utc_now)
    last_seen_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    # Last day a cinema announced it (prossimamente): a film never screened leaves when this gets old
    last_announced_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    is_event: Mapped[bool] = mapped_column(Boolean, default=False)
    consecutive_missing_days: Mapped[int] = mapped_column(Integer, default=0)
    runtime: Mapped[int | None] = mapped_column(Integer, nullable=True)  # minutes, from the TMDB details
    genre: Mapped[str | None] = mapped_column(String(50), nullable=True)  # main genre, from the TMDB details
    details_tmdb_id: Mapped[int | None] = mapped_column(Integer, nullable=True)  # TMDB film runtime/genre belong to
    # Plot, director(s) and main cast from TMDB ("A, B"), and the TMDB film they belong to
    overview: Mapped[str | None] = mapped_column(Text, nullable=True)
    director: Mapped[str | None] = mapped_column(String(300), nullable=True)
    cast_names: Mapped[str | None] = mapped_column(String(500), nullable=True)
    credits_tmdb_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # The phone was notified that it arrived in theaters (app/push.py)
    in_sala_pushed: Mapped[bool] = mapped_column(Boolean, default=False)

    showtimes: Mapped[list[Showtime]] = relationship(back_populates="film", cascade="all, delete-orphan")
    snapshots: Mapped[list[DailySnapshot]] = relationship(back_populates="film", cascade="all, delete-orphan")
    aliases: Mapped[list[FilmAlias]] = relationship(back_populates="film", cascade="all, delete-orphan")
    coming_soon: Mapped[list[ComingSoon]] = relationship(back_populates="film", cascade="all, delete-orphan")
    last_days: Mapped[list[LastDays]] = relationship(back_populates="film", cascade="all, delete-orphan")

    @property
    def is_tmdb_confirmed(self) -> bool:
        return self.tmdb_id is not None and self.tmdb_match_status in ("abbinato", "manuale")

    @property
    def has_tmdb_details(self) -> bool:
        """Runtime and genre are known and belong to the confirmed TMDB match."""
        return self.is_tmdb_confirmed and self.details_tmdb_id == self.tmdb_id

    @property
    def has_tmdb_credits(self) -> bool:
        """Plot, director and cast are known and belong to the confirmed TMDB match."""
        return self.is_tmdb_confirmed and self.credits_tmdb_id == self.tmdb_id

    def __repr__(self) -> str:
        return f"<Film {self.raw_title!r} status={self.status}>"


class FilmAlias(Base):
    """Other normalized titles of a film, kept after merging duplicates.

    Lets a later scrape of e.g. "mammina (other mommy)" land on the merged "MAMMINA".
    """

    __tablename__ = "film_aliases"

    id: Mapped[int] = mapped_column(primary_key=True)
    normalized_title: Mapped[str] = mapped_column(String(300), unique=True, index=True)
    film_id: Mapped[int] = mapped_column(ForeignKey("films.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utc_now)

    film: Mapped[Film] = relationship(back_populates="aliases")

    def __repr__(self) -> str:
        return f"<FilmAlias {self.normalized_title!r} -> {self.film_id}>"


class FilmMerge(Base):
    """A duplicate film merged into another: deleted id -> id of the film that absorbed it.

    The phone keeps votes by film id: with this list it moves a vote given to the deleted
    copy onto the surviving film. New films never reuse an id listed here.
    """

    __tablename__ = "film_merges"

    old_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False)
    new_id: Mapped[int] = mapped_column(Integer, index=True)
    merged_at: Mapped[datetime] = mapped_column(DateTime, default=_utc_now)

    def __repr__(self) -> str:
        return f"<FilmMerge {self.old_id} -> {self.new_id}>"


class LastDays(Base):
    """A guess that a film is in its last days: the cinemas publish later days without it.

    One row per film and guessed last day, kept to check the guesses afterwards
    (``python -m app.push verifica``) and to notify each one once.
    """

    __tablename__ = "last_days"
    __table_args__ = (UniqueConstraint("film_id", "last_day", name="uq_last_days_film_day"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    film_id: Mapped[int] = mapped_column(ForeignKey("films.id"), index=True)
    last_day: Mapped[date] = mapped_column(Date)
    found_on: Mapped[date] = mapped_column(Date)  # first sync that guessed it
    notified: Mapped[bool] = mapped_column(Boolean, default=False)

    film: Mapped[Film] = relationship(back_populates="last_days")

    def __repr__(self) -> str:
        return f"<LastDays film={self.film_id} until={self.last_day}>"


class ComingSoon(Base):
    """A film announced by a cinema ("prossimamente"), possibly without showtimes or date yet.

    One row per film, cinema and source page; rows disappear when the source stops listing them.
    """

    __tablename__ = "coming_soon"
    __table_args__ = (UniqueConstraint("film_id", "cinema_id", "source", name="uq_coming_soon_film_cinema_source"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    film_id: Mapped[int] = mapped_column(ForeignKey("films.id"), index=True)
    cinema_id: Mapped[int] = mapped_column(ForeignKey("cinemas.id"), index=True)
    source: Mapped[str] = mapped_column(String(50))  # cinema slug or coming-soon source slug
    release_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    tags: Mapped[str | None] = mapped_column(String(200), nullable=True)
    source_url: Mapped[str] = mapped_column(String(500), default="")
    first_seen: Mapped[datetime] = mapped_column(DateTime, default=_utc_now)
    last_seen: Mapped[datetime] = mapped_column(DateTime, default=_utc_now)

    film: Mapped[Film] = relationship(back_populates="coming_soon")
    cinema: Mapped[Cinema] = relationship()

    def __repr__(self) -> str:
        return f"<ComingSoon film={self.film_id} cinema={self.cinema_id} {self.release_date} ({self.source})>"


class Showtime(Base):
    __tablename__ = "showtimes"

    id: Mapped[int] = mapped_column(primary_key=True)
    film_id: Mapped[int] = mapped_column(ForeignKey("films.id"), index=True)
    cinema_id: Mapped[int] = mapped_column(ForeignKey("cinemas.id"), index=True)
    date: Mapped[date] = mapped_column(Date, index=True)
    time: Mapped[time] = mapped_column(Time)
    sala: Mapped[str | None] = mapped_column(String(50), nullable=True)
    tags: Mapped[str | None] = mapped_column(String(200), nullable=True)
    source_url: Mapped[str] = mapped_column(String(500))
    booking_url: Mapped[str | None] = mapped_column(String(500), nullable=True)  # buy this screening
    last_seen: Mapped[datetime] = mapped_column(DateTime, default=_utc_now)
    scraped_at: Mapped[datetime] = mapped_column(DateTime, default=_utc_now)

    film: Mapped[Film] = relationship(back_populates="showtimes")
    cinema: Mapped[Cinema] = relationship(back_populates="showtimes")

    def __init__(self, **kwargs):
        # Support Italian aliases in constructor
        if "data" in kwargs and "date" not in kwargs:
            kwargs["date"] = kwargs.pop("data")
        if "ora" in kwargs and "time" not in kwargs:
            kwargs["time"] = kwargs.pop("ora")
        if "url" in kwargs and "source_url" not in kwargs:
            kwargs["source_url"] = kwargs.pop("url")
        if "visto_l_ultima_volta" in kwargs and "last_seen" not in kwargs:
            kwargs["last_seen"] = kwargs.pop("visto_l_ultima_volta")
        super().__init__(**kwargs)

    @property
    def data(self) -> date:
        return self.date

    @data.setter
    def data(self, value: date) -> None:
        self.date = value

    @property
    def ora(self) -> time:
        return self.time

    @ora.setter
    def ora(self, value: time) -> None:
        self.time = value

    @property
    def url(self) -> str:
        return self.source_url

    @url.setter
    def url(self, value: str) -> None:
        self.source_url = value

    @property
    def visto_l_ultima_volta(self) -> datetime:
        return self.last_seen

    @visto_l_ultima_volta.setter
    def visto_l_ultima_volta(self, value: datetime) -> None:
        self.last_seen = value

    def __repr__(self) -> str:
        return f"<Showtime {self.film_id} @ {self.cinema_id} {self.date} {self.time}>"


class DailySnapshot(Base):
    """Daily snapshot of films present in each cinema."""

    __tablename__ = "daily_snapshots"
    __table_args__ = (
        UniqueConstraint("sync_date", "cinema_id", "film_id", name="uq_daily_snapshots_date_cinema_film"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    sync_date: Mapped[date] = mapped_column(Date, index=True)
    cinema_id: Mapped[int] = mapped_column(ForeignKey("cinemas.id"), index=True)
    film_id: Mapped[int] = mapped_column(ForeignKey("films.id"), index=True)
    showtimes_count: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utc_now)

    film: Mapped[Film] = relationship(back_populates="snapshots")
    cinema: Mapped[Cinema] = relationship(back_populates="snapshots")

    def __repr__(self) -> str:
        return f"<DailySnapshot date={self.sync_date} cinema={self.cinema_id} film={self.film_id}>"


class SyncRun(Base):
    """Audit record for a sync operation for a specific cinema."""

    __tablename__ = "sync_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    sync_date: Mapped[date] = mapped_column(Date, index=True)
    cinema_id: Mapped[int] = mapped_column(ForeignKey("cinemas.id"), index=True)
    status: Mapped[str] = mapped_column(String(50))  # "ok", "error", "empty_anomaly"
    showtimes_count: Mapped[int] = mapped_column(Integer, default=0)
    error_message: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utc_now)

    cinema: Mapped[Cinema] = relationship()

    def __repr__(self) -> str:
        return f"<SyncRun date={self.sync_date} cinema={self.cinema_id} status={self.status}>"


class SyncLog(Base):
    """One full sync (all cinemas): when, who started it, outcome and backup taken before it."""

    __tablename__ = "sync_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=_utc_now, index=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    trigger: Mapped[str] = mapped_column(String(20))  # "manuale" | "automatico" | "terminale"
    ok: Mapped[bool] = mapped_column(Boolean, default=False)
    films_total: Mapped[int] = mapped_column(Integer, default=0)
    new_films: Mapped[int] = mapped_column(Integer, default=0)
    showtimes: Mapped[int] = mapped_column(Integer, default=0)
    errors: Mapped[str | None] = mapped_column(String(2000), nullable=True)  # one per line
    backup_file: Mapped[str | None] = mapped_column(String(300), nullable=True)

    def __repr__(self) -> str:
        return f"<SyncLog {self.started_at} {self.trigger} ok={self.ok}>"
