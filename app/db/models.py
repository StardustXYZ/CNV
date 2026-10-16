"""ORM models – Cinema, Film, Showtime."""

from __future__ import annotations

from datetime import date, datetime, time, timezone

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, String, Time
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

    def __repr__(self) -> str:
        return f"<Cinema {self.slug!r}>"


class Film(Base):
    __tablename__ = "films"

    id: Mapped[int] = mapped_column(primary_key=True)
    raw_title: Mapped[str] = mapped_column(String(300))
    normalized_title: Mapped[str] = mapped_column(String(300), index=True)
    tmdb_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tmdb_title: Mapped[str | None] = mapped_column(String(300), nullable=True)
    poster_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    vote: Mapped[str | None] = mapped_column(String(1), nullable=True)  # V | ? | X
    in_theaters: Mapped[bool] = mapped_column(Boolean, default=True)
    first_seen: Mapped[datetime] = mapped_column(DateTime, default=_utc_now)
    last_seen: Mapped[datetime] = mapped_column(DateTime, default=_utc_now)
    exported_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    showtimes: Mapped[list[Showtime]] = relationship(back_populates="film")

    def __repr__(self) -> str:
        return f"<Film {self.raw_title!r} vote={self.vote}>"


class Showtime(Base):
    __tablename__ = "showtimes"

    id: Mapped[int] = mapped_column(primary_key=True)
    film_id: Mapped[int] = mapped_column(ForeignKey("films.id"))
    cinema_id: Mapped[int] = mapped_column(ForeignKey("cinemas.id"))
    date: Mapped[date] = mapped_column(Date)
    time: Mapped[time] = mapped_column(Time)
    sala: Mapped[str | None] = mapped_column(String(50), nullable=True)
    tags: Mapped[str | None] = mapped_column(String(200), nullable=True)
    source_url: Mapped[str] = mapped_column(String(500))
    scraped_at: Mapped[datetime] = mapped_column(DateTime, default=_utc_now)

    film: Mapped[Film] = relationship(back_populates="showtimes")
    cinema: Mapped[Cinema] = relationship(back_populates="showtimes")

    def __repr__(self) -> str:
        return f"<Showtime {self.film_id} @ {self.cinema_id} {self.date} {self.time}>"

