"""ORM models – Cinema, Film, FilmAlias, ComingSoon, Showtime, DailySnapshot, SyncRun."""

from __future__ import annotations

from datetime import date, datetime, time, timezone

from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, Integer, String, Time, UniqueConstraint
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
    vote: Mapped[str | None] = mapped_column(String(1), nullable=True)  # stato_utente: V / ? / X / None
    status: Mapped[str] = mapped_column(String(50), default="in_uscita", index=True)  # in_uscita | in_sala | uscito
    left_theaters_date: Mapped[date | None] = mapped_column(Date, nullable=True)  # data_uscita_dalle_sale
    letterboxd_exported: Mapped[bool] = mapped_column(Boolean, default=False)  # esportato_letterboxd
    in_theaters: Mapped[bool] = mapped_column(Boolean, default=True)
    first_seen: Mapped[datetime] = mapped_column(DateTime, default=_utc_now)
    last_seen: Mapped[datetime] = mapped_column(DateTime, default=_utc_now)
    last_seen_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    exported_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    is_event: Mapped[bool] = mapped_column(Boolean, default=False)
    consecutive_missing_days: Mapped[int] = mapped_column(Integer, default=0)

    showtimes: Mapped[list[Showtime]] = relationship(back_populates="film", cascade="all, delete-orphan")
    snapshots: Mapped[list[DailySnapshot]] = relationship(back_populates="film", cascade="all, delete-orphan")
    aliases: Mapped[list[FilmAlias]] = relationship(back_populates="film", cascade="all, delete-orphan")
    coming_soon: Mapped[list[ComingSoon]] = relationship(back_populates="film", cascade="all, delete-orphan")

    @property
    def is_tmdb_confirmed(self) -> bool:
        return self.tmdb_id is not None and self.tmdb_match_status in ("abbinato", "manuale")

    def __init__(self, **kwargs):
        # Support Italian aliases in constructor
        if "titolo" in kwargs and "raw_title" not in kwargs:
            kwargs["raw_title"] = kwargs.pop("titolo")
        if "anno" in kwargs and "year" not in kwargs:
            kwargs["year"] = kwargs.pop("anno")
        if "stato_utente" in kwargs and "vote" not in kwargs:
            kwargs["vote"] = kwargs.pop("stato_utente")
        if "stato_programmazione" in kwargs and "status" not in kwargs:
            kwargs["status"] = kwargs.pop("stato_programmazione")
        if "data_uscita_dalle_sale" in kwargs and "left_theaters_date" not in kwargs:
            kwargs["left_theaters_date"] = kwargs.pop("data_uscita_dalle_sale")
        if "esportato_letterboxd" in kwargs and "letterboxd_exported" not in kwargs:
            kwargs["letterboxd_exported"] = kwargs.pop("esportato_letterboxd")
        if "consecutive_missing_syncs" in kwargs and "consecutive_missing_days" not in kwargs:
            kwargs["consecutive_missing_days"] = kwargs.pop("consecutive_missing_syncs")
        super().__init__(**kwargs)

    @property
    def consecutive_missing_syncs(self) -> int:
        return self.consecutive_missing_days

    @consecutive_missing_syncs.setter
    def consecutive_missing_syncs(self, value: int) -> None:
        self.consecutive_missing_days = value

    @property
    def titolo(self) -> str:
        return self.raw_title

    @titolo.setter
    def titolo(self, value: str) -> None:
        self.raw_title = value

    @property
    def anno(self) -> int | None:
        return self.year

    @anno.setter
    def anno(self, value: int | None) -> None:
        self.year = value

    @property
    def stato_utente(self) -> str | None:
        return self.vote

    @stato_utente.setter
    def stato_utente(self, value: str | None) -> None:
        self.vote = value

    @property
    def stato_programmazione(self) -> str:
        return self.status

    @stato_programmazione.setter
    def stato_programmazione(self, value: str) -> None:
        self.status = value

    @property
    def data_uscita_dalle_sale(self) -> date | None:
        return self.left_theaters_date

    @data_uscita_dalle_sale.setter
    def data_uscita_dalle_sale(self, value: date | None) -> None:
        self.left_theaters_date = value

    @property
    def esportato_letterboxd(self) -> bool:
        return self.letterboxd_exported

    @esportato_letterboxd.setter
    def esportato_letterboxd(self, value: bool) -> None:
        self.letterboxd_exported = value

    def __repr__(self) -> str:
        return f"<Film {self.raw_title!r} status={self.status} vote={self.vote}>"


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
