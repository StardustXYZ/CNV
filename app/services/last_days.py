"""Films in their last days: a cinema has published later days, and they are not there.

Each cinema publishes its programme a few days ahead (2 to 4, with some presales much
further). A cinema's programme counts as published up to the last day that has at least
half of today's films: later days only hold presales. A film whose shows at a cinema
stop before that day has been left out of the days already published: it is leaving.

A film is in its last days when it is leaving every cinema that still shows it; its last
day is the latest of those. Events are left out (they last a few days by nature).
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date

from sqlalchemy.orm import Session

from app.db.models import Film, LastDays, Showtime


@dataclass
class LeavingFilm:
    film: Film
    last_day: date


def published_until(days_by_film: dict[int, set[date]], today: date) -> date | None:
    """The last day a cinema has really published (None: it shows nothing today)."""
    today_films = sum(1 for days in days_by_film.values() if today in days)
    if not today_films:
        return None
    films_on: dict[date, int] = defaultdict(int)
    for days in days_by_film.values():
        for d in days:
            films_on[d] += 1
    return max(d for d, n in films_on.items() if d >= today and 2 * n >= today_films)


def leaving_films(db: Session, today: date) -> list[LeavingFilm]:
    """The films in their last days, the soonest to leave first."""
    days: dict[int, dict[int, set[date]]] = defaultdict(lambda: defaultdict(set))  # cinema -> film -> days
    for film_id, cinema_id, day in db.query(Showtime.film_id, Showtime.cinema_id, Showtime.date).filter(
        Showtime.date >= today
    ):
        days[cinema_id][film_id].add(day)

    leaving: dict[int, list[date]] = defaultdict(list)  # film -> its last day at each cinema it leaves
    staying: set[int] = set()
    for by_film in days.values():
        until = published_until(by_film, today)
        for film_id, film_days in by_film.items():
            last = max(film_days)
            if until is not None and last < until:
                leaving[film_id].append(last)
            else:
                staying.add(film_id)  # still there on the last published day, or no way to tell

    films = {f.id: f for f in db.query(Film).filter(Film.id.in_(leaving), Film.status == "in_sala")}
    result = [
        LeavingFilm(films[film_id], max(lasts))
        for film_id, lasts in leaving.items()
        if film_id not in staying and film_id in films and not films[film_id].is_event
    ]
    return sorted(result, key=lambda lf: (lf.last_day, lf.film.raw_title.lower()))


def record_leaving(db: Session, today: date) -> list[LeavingFilm]:
    """Find the films in their last days and keep each new guess (for the check and the notice)."""
    found = leaving_films(db, today)
    for lf in found:
        exists = db.query(LastDays).filter_by(film_id=lf.film.id, last_day=lf.last_day).first()
        if exists is None:
            db.add(LastDays(film_id=lf.film.id, last_day=lf.last_day, found_on=today))
    db.commit()
    return found


@dataclass
class GuessCheck:
    title: str
    found_on: date
    last_day: date
    real_last_day: date | None  # the last show it really had (None: none at all)

    @property
    def right(self) -> bool:
        return self.real_last_day is not None and self.real_last_day <= self.last_day


def check_guesses(db: Session, today: date) -> list[GuessCheck]:
    """The guesses whose last day is over, compared with the shows the film really had."""
    checks = []
    for guess in db.query(LastDays).filter(LastDays.last_day < today).order_by(LastDays.found_on, LastDays.id):
        shows = [s.date for s in guess.film.showtimes if s.date >= guess.found_on]
        film = guess.film
        title = film.tmdb_title if film.is_tmdb_confirmed and film.tmdb_title else film.raw_title
        checks.append(GuessCheck(title, guess.found_on, guess.last_day, max(shows, default=None)))
    return checks
