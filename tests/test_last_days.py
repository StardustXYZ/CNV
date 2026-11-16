"""Tests for the films in their last days (app/services/last_days.py)."""

from __future__ import annotations

from datetime import date, time, timedelta

from app.db.models import Cinema, Film, LastDays, Showtime
from app.services.last_days import check_guesses, leaving_films, published_until, record_leaving

TODAY = date(2026, 11, 16)


def day(n: int) -> date:
    return TODAY + timedelta(days=n)


def test_published_until_is_the_last_day_with_half_of_todays_films():
    # 4 films today; tomorrow 3, the day after 2 (half: still published), then a presale alone
    films = {
        1: {day(0), day(1), day(2)},
        2: {day(0), day(1), day(2)},
        3: {day(0), day(1)},
        4: {day(0)},
        5: {day(30)},
    }
    assert published_until(films, TODAY) == day(2)
    assert published_until({5: {day(30)}}, TODAY) is None  # nothing today: no way to tell


def _cinema(db, slug):
    c = Cinema(slug=slug, name=slug.title(), url=f"https://{slug}.example")
    db.add(c)
    db.flush()
    return c


def _film(db, title, **fields):
    f = Film(raw_title=title, normalized_title=title.lower(), status=fields.pop("status", "in_sala"), **fields)
    db.add(f)
    db.flush()
    return f


def _shows(db, film, cinema, *days):
    for n in days:
        db.add(Showtime(film_id=film.id, cinema_id=cinema.id, date=day(n), time=time(21, 0), source_url=""))


def test_a_film_leaves_when_every_cinema_published_later_days_without_it(db):
    andromeda, garden = _cinema(db, "andromeda"), _cinema(db, "garden")
    stays = [_film(db, f"Resta {n}") for n in range(3)]
    leaves = _film(db, "Se ne va")
    one_of_two = _film(db, "Resta al Garden")
    event = _film(db, "Concerto", is_event=True)
    presale = _film(db, "Prevendita", status="in_uscita")
    # Andromeda: 6 films today, 4 tomorrow, 3 the day after (half: published up to day 2)
    for f in stays:
        _shows(db, f, andromeda, 0, 1, 2)
    _shows(db, leaves, andromeda, 0, 1)  # left out of day 2
    _shows(db, one_of_two, andromeda, 0)
    _shows(db, event, andromeda, 0)
    _shows(db, presale, andromeda, 20)
    # The Garden publishes 2 days; there "Se ne va" stops today, "Resta al Garden" goes on
    other = _film(db, "Altro")
    _shows(db, other, garden, 0, 1)
    _shows(db, leaves, garden, 0)
    _shows(db, one_of_two, garden, 0, 1)
    db.commit()

    found = leaving_films(db, TODAY)
    assert [(lf.film.raw_title, lf.last_day) for lf in found] == [("Se ne va", day(1))]  # the latest of its cinemas


def test_guesses_are_kept_once_and_checked_against_the_real_shows(db):
    andromeda = _cinema(db, "andromeda")
    stays, leaves = _film(db, "Resta"), _film(db, "Se ne va")
    _shows(db, stays, andromeda, 0, 1, 2)
    _shows(db, leaves, andromeda, 0, 1)
    db.commit()

    record_leaving(db, TODAY)
    record_leaving(db, TODAY)  # the second run of the night: no new row
    guess = db.query(LastDays).one()
    assert (guess.film_id, guess.last_day, guess.found_on, guess.notified) == (leaves.id, day(1), TODAY, False)

    assert check_guesses(db, day(1)) == []  # its last day is not over yet
    (check,) = check_guesses(db, day(2))
    assert check.right and check.real_last_day == day(1)

    # Then the cinema put it back on day 3: the guess was wrong
    _shows(db, leaves, andromeda, 3)
    db.commit()
    (check,) = check_guesses(db, day(4))
    assert not check.right and check.real_last_day == day(3)
