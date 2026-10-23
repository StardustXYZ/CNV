"""Tests for the sync service and lifecycle scenarios."""

from __future__ import annotations

from datetime import date, time
import pytest

from app.config import CinemaConfig
from app.db.models import Cinema, DailySnapshot, Film, Showtime, SyncRun
from app.scrapers.base import ShowtimeData
from app.services.sync import is_event_film, normalize_title, run_sync


def test_normalize_basic():
    assert normalize_title("  Il Gladiatore II  ") == "il gladiatore ii"


def test_normalize_accents():
    assert normalize_title("Città di Dio") == "citta di dio"


def test_normalize_punctuation():
    assert normalize_title("Napoli – New York") == "napoli new york"


def test_normalize_apostrophe():
    # Apostrophe and similar chars are stripped
    result = normalize_title("L'Amore è Bello")
    assert "lamore" in result
    assert "bello" in result


# ------------------------------------------------------------------
# Simulated Scenario Tests
# ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_scenario_prevendita_che_diventa_in_sala(db):
    """Scenario 1: Advance pre-sale in the future starts as 'in_uscita'.

    When the date reaches the screening, it transitions to 'in_sala'.
    """
    cinemas = [
        CinemaConfig(slug="andromeda", name="Andromeda River", url="https://example.com", scraper="stub"),
    ]

    # Day 1: 18 October 2026. Showtime is in December 2026 (> today).
    oct_shows = [
        ShowtimeData(
            cinema="andromeda",
            raw_title="AVENGERS: DOOMSDAY - DAL 16 DICEMBRE",
            date=date(2026, 12, 16),
            time=time(20, 30),
            sala="Sala 1",
            source_url="https://example.com/avengers",
        )
    ]
    res_oct = await run_sync(
        db,
        as_of_date=date(2026, 10, 18),
        cinemas=cinemas,
        scraper_results={"andromeda": oct_shows},
    )

    film = db.query(Film).first()
    assert film.raw_title == "AVENGERS: DOOMSDAY"
    assert film.status == "in_uscita"
    assert film.stato_programmazione == "in_uscita"
    assert film.data_uscita_dalle_sale is None

    # Day 60: 16 December 2026. Showtime is today.
    dec_shows = [
        ShowtimeData(
            cinema="andromeda",
            raw_title="AVENGERS: DOOMSDAY",
            date=date(2026, 12, 16),
            time=time(20, 30),
            sala="Sala 1",
            source_url="https://example.com/avengers",
        )
    ]
    res_dec = await run_sync(
        db,
        as_of_date=date(2026, 12, 16),
        cinemas=cinemas,
        scraper_results={"andromeda": dec_shows},
    )

    db.refresh(film)
    assert film.status == "in_sala"
    assert film.stato_programmazione == "in_sala"
    assert film.in_theaters is True

    # Verify state transition was logged
    changes = [c for c in res_dec.status_changes if c.film_id == film.id]
    assert any(c.old_status == "in_uscita" and c.new_status == "in_sala" for c in changes)


@pytest.mark.asyncio
async def test_scenario_sparizione_breve_tolleranza_buchi(db):
    """Scenario 2: Film disappears for 2 days and reappears.

    It should NOT be marked 'uscito', and remain 'in_sala'.
    """
    cinemas = [
        CinemaConfig(slug="andromeda", name="Andromeda River", url="https://example.com", scraper="stub"),
    ]

    # Day 1 (18/10): Film in theater
    day1_shows = [
        ShowtimeData(
            cinema="andromeda",
            raw_title="Parthenope",
            date=date(2026, 10, 18),
            time=time(18, 0),
            sala="Sala 2",
            source_url="https://example.com/parthenope",
        )
    ]
    await run_sync(db, as_of_date=date(2026, 10, 18), cinemas=cinemas, scraper_results={"andromeda": day1_shows})

    film = db.query(Film).first()
    assert film.status == "in_sala"
    assert film.consecutive_missing_syncs == 0

    # Day 2 (19/10): Missing for 1 day, cinema is open with other films
    other_day2 = [ShowtimeData(cinema="andromeda", raw_title="Altro Film", date=date(2026, 10, 19), time=time(18, 0))]
    await run_sync(db, as_of_date=date(2026, 10, 19), cinemas=cinemas, scraper_results={"andromeda": other_day2})
    db.refresh(film)
    assert film.status == "in_sala"
    assert film.consecutive_missing_syncs == 1

    # Day 3 (20/10): Missing for 2 days
    other_day3 = [ShowtimeData(cinema="andromeda", raw_title="Altro Film", date=date(2026, 10, 20), time=time(18, 0))]
    await run_sync(db, as_of_date=date(2026, 10, 20), cinemas=cinemas, scraper_results={"andromeda": other_day3})
    db.refresh(film)
    assert film.status == "in_sala"
    assert film.consecutive_missing_syncs == 2
    assert film.data_uscita_dalle_sale is None

    # Day 4 (21/10): Reappears!
    day4_shows = [
        ShowtimeData(
            cinema="andromeda",
            raw_title="Parthenope",
            date=date(2026, 10, 21),
            time=time(20, 0),
            sala="Sala 2",
            source_url="https://example.com/parthenope",
        )
    ]
    await run_sync(db, as_of_date=date(2026, 10, 21), cinemas=cinemas, scraper_results={"andromeda": day4_shows})
    db.refresh(film)
    assert film.status == "in_sala"
    assert film.consecutive_missing_syncs == 0
    assert film.data_uscita_dalle_sale is None


@pytest.mark.asyncio
async def test_scenario_sparizione_definitiva_7_giorni(db):
    """Scenario 3: Film disappears for 7 consecutive days (default threshold).

    It transitions to 'uscito' and records data_uscita_dalle_sale.
    """
    cinemas = [
        CinemaConfig(slug="andromeda", name="Andromeda River", url="https://example.com", scraper="stub"),
    ]

    # Day 1 (01/10): Film in theater with standard 7-day weekly programming
    day1_shows = [
        ShowtimeData(
            cinema="andromeda",
            raw_title="Saw X",
            date=date(2026, 10, i),
            time=time(21, 0),
            sala="Sala 1",
            source_url="https://example.com/saw",
        )
        for i in range(1, 8)
    ]
    await run_sync(db, as_of_date=date(2026, 10, 1), cinemas=cinemas, scraper_results={"andromeda": day1_shows})

    film = db.query(Film).first()
    assert film.status == "in_sala"
    assert is_event_film(film) is False

    # Missing from Day 2 to Day 7 (6 days missing -> still in_sala)
    for day_num in range(2, 8):
        current_d = date(2026, 10, day_num)
        other_shows = [ShowtimeData(cinema="andromeda", raw_title="Altro Film", date=current_d, time=time(18, 0))]
        await run_sync(db, as_of_date=current_d, cinemas=cinemas, scraper_results={"andromeda": other_shows})
        db.refresh(film)
        assert film.status == "in_sala"
        assert film.consecutive_missing_syncs == day_num - 1

    # Day 8: 7 consecutive missing syncs reached (threshold N=7)!
    day8 = date(2026, 10, 8)
    other_day8 = [ShowtimeData(cinema="andromeda", raw_title="Altro Film", date=day8, time=time(18, 0))]
    res = await run_sync(db, as_of_date=day8, cinemas=cinemas, scraper_results={"andromeda": other_day8})
    db.refresh(film)
    assert film.status == "uscito"
    assert film.in_theaters is False
    assert film.data_uscita_dalle_sale == day8

    changes = [c for c in res.status_changes if c.film_id == film.id]
    assert any(c.new_status == "uscito" for c in changes)


@pytest.mark.asyncio
async def test_scenario_evento_3_giorni(db):
    """Scenario 4: Film marked as an EVENT has threshold N=3 days."""
    cinemas = [
        CinemaConfig(slug="andromeda", name="Andromeda River", url="https://example.com", scraper="stub"),
    ]

    # Day 1: Film with EVENTO tag
    day1_shows = [
        ShowtimeData(
            cinema="andromeda",
            raw_title="EVENTO 8 TRAINSPOTTING 30° ANNIVERSARIO",
            date=date(2026, 10, 1),
            time=time(20, 30),
            sala="Sala 1",
            tags=["EVENTO 8"],
            source_url="https://example.com/trainspotting",
        )
    ]
    await run_sync(db, as_of_date=date(2026, 10, 1), cinemas=cinemas, scraper_results={"andromeda": day1_shows})

    film = db.query(Film).first()
    assert film.status == "in_sala"
    assert is_event_film(film) is True
    assert film.is_event is True

    # Day 2: Missing day 1
    other_day2 = [ShowtimeData(cinema="andromeda", raw_title="Altro Film", date=date(2026, 10, 2), time=time(18, 0))]
    await run_sync(db, as_of_date=date(2026, 10, 2), cinemas=cinemas, scraper_results={"andromeda": other_day2})
    db.refresh(film)
    assert film.status == "in_sala"
    assert film.consecutive_missing_syncs == 1

    # Day 3: Missing day 2
    other_day3 = [ShowtimeData(cinema="andromeda", raw_title="Altro Film", date=date(2026, 10, 3), time=time(18, 0))]
    await run_sync(db, as_of_date=date(2026, 10, 3), cinemas=cinemas, scraper_results={"andromeda": other_day3})
    db.refresh(film)
    assert film.status == "in_sala"
    assert film.consecutive_missing_syncs == 2

    # Day 4: Missing day 3 -> threshold N=3 reached for event!
    day4 = date(2026, 10, 4)
    other_day4 = [ShowtimeData(cinema="andromeda", raw_title="Altro Film", date=day4, time=time(18, 0))]
    await run_sync(db, as_of_date=day4, cinemas=cinemas, scraper_results={"andromeda": other_day4})
    db.refresh(film)
    assert film.status == "uscito"
    assert film.data_uscita_dalle_sale == day4



@pytest.mark.asyncio
async def test_scenario_scraper_rotto_non_considera_spariti(db):
    """Scenario 5: If a scraper fails or returns 0 shows anomalously,

    films from that cinema are NOT considered missing and not marked 'uscito'.
    """
    cinemas = [
        CinemaConfig(slug="citrigno", name="Cinema Citrigno", url="https://citrigno.example.com", scraper="18tickets"),
        CinemaConfig(slug="andromeda", name="Andromeda River", url="https://andromeda.example.com", scraper="18tickets"),
    ]

    # Day 1: Film 'Zustissia' is playing exclusively at Citrigno
    day1_shows = {
        "citrigno": [
            ShowtimeData(
                cinema="citrigno",
                raw_title="Zustissia",
                date=date(2026, 10, 1),
                time=time(18, 0),
                sala="Sala 1",
                source_url="https://citrigno.example.com/zustissia",
            )
        ],
        "andromeda": [
            ShowtimeData(
                cinema="andromeda",
                raw_title="Another Film",
                date=date(2026, 10, 1),
                time=time(20, 0),
                sala="Sala A",
                source_url="https://andromeda.example.com/another",
            )
        ],
    }
    await run_sync(db, as_of_date=date(2026, 10, 1), cinemas=cinemas, scraper_results=day1_shows)

    film_zustissia = db.query(Film).filter_by(normalized_title="zustissia").first()
    assert film_zustissia.status == "in_sala"

    # Day 2: Citrigno scraper crashes with RuntimeError, while Andromeda succeeds
    day2_andromeda = {
        "andromeda": [
            ShowtimeData(
                cinema="andromeda",
                raw_title="Another Film",
                date=date(2026, 10, 2),
                time=time(20, 0),
                sala="Sala A",
                source_url="https://andromeda.example.com/another",
            )
        ]
    }
    errors = {"citrigno": RuntimeError("503 Service Unavailable")}

    res_day2 = await run_sync(
        db,
        as_of_date=date(2026, 10, 2),
        cinemas=cinemas,
        scraper_results=day2_andromeda,
        scraper_errors=errors,
    )

    db.refresh(film_zustissia)
    # The film must NOT have its missing counter incremented, must remain in_sala
    assert film_zustissia.status == "in_sala"
    assert film_zustissia.consecutive_missing_syncs == 0
    assert "citrigno" in res_day2.errors

    # Verify audit SyncRun table logged the failure
    citrigno_cinema = db.query(Cinema).filter_by(slug="citrigno").first()
    sync_run = db.query(SyncRun).filter_by(sync_date=date(2026, 10, 2), cinema_id=citrigno_cinema.id).first()
    assert sync_run is not None
    assert sync_run.status == "error"


@pytest.mark.asyncio
async def test_scenario_ricomparsa_dopo_uscito_azzera_data(db):
    """Scenario 6: Film marked 'uscito' returns to theaters.

    Transitions back to 'in_sala' and resets data_uscita_dalle_sale to None.
    """
    cinemas = [
        CinemaConfig(slug="garden", name="Cinema Garden", url="https://example.com", scraper="garden"),
    ]

    # Pre-existing film that was marked uscito
    film = Film(
        raw_title="Cinecittà",
        normalized_title="cinecitta",
        status="uscito",
        in_theaters=False,
        left_theaters_date=date(2026, 9, 30),
        consecutive_missing_syncs=10,
    )
    db.add(film)
    db.commit()

    # Film reappears with new showtimes today
    today = date(2026, 10, 18)
    garden_shows = [
        ShowtimeData(
            cinema="Cinema Garden",
            raw_title="Cinecittà",
            date=today,
            time=time(21, 0),
            sala="Sala Garden",
            source_url="https://example.com/cinecitta",
        )
    ]
    res = await run_sync(
        db,
        as_of_date=today,
        cinemas=cinemas,
        scraper_results={"garden": garden_shows},
    )

    db.refresh(film)
    assert film.status == "in_sala"
    assert film.in_theaters is True
    assert film.data_uscita_dalle_sale is None
    assert film.left_theaters_date is None
    assert film.consecutive_missing_syncs == 0

    reappeared_changes = [c for c in res.status_changes if c.change_type == "reappeared"]
    assert len(reappeared_changes) == 1
    assert reappeared_changes[0].film_id == film.id


@pytest.mark.asyncio
async def test_scenario_daily_snapshots(db):
    """Scenario 7: Daily snapshots table accurately records film presence per cinema."""
    cinemas = [
        CinemaConfig(slug="garden", name="Cinema Garden", url="https://example.com", scraper="garden"),
        CinemaConfig(slug="citrigno", name="Cinema Citrigno", url="https://example.com", scraper="18tickets"),
    ]

    sync_d = date(2026, 10, 18)
    scraped = {
        "garden": [
            ShowtimeData(cinema="Cinema Garden", raw_title="Film 1", date=sync_d, time=time(18, 0)),
            ShowtimeData(cinema="Cinema Garden", raw_title="Film 1", date=sync_d, time=time(20, 30)),
        ],
        "citrigno": [
            ShowtimeData(cinema="citrigno", raw_title="Film 2", date=sync_d, time=time(19, 0)),
        ],
    }

    res = await run_sync(db, as_of_date=sync_d, cinemas=cinemas, scraper_results=scraped)
    assert res.snapshots_created == 2

    # Verify query on DailySnapshot table
    snaps = db.query(DailySnapshot).filter_by(sync_date=sync_d).all()
    assert len(snaps) == 2

    garden_snap = [s for s in snaps if s.cinema.slug == "garden"][0]
    assert garden_snap.film.raw_title == "Film 1"
    assert garden_snap.showtimes_count == 2

    citrigno_snap = [s for s in snaps if s.cinema.slug == "citrigno"][0]
    assert citrigno_snap.film.raw_title == "Film 2"
    assert citrigno_snap.showtimes_count == 1

    # Second sync on same day: snapshots are updated, not created
    res2 = await run_sync(db, as_of_date=sync_d, cinemas=cinemas, scraper_results=scraped)
    assert res2.snapshots_created == 0
    assert res2.snapshots_updated == 2

    # Verify at most one snapshot per (sync_date, cinema_id, film_id)
    all_snaps = db.query(DailySnapshot).filter_by(sync_date=sync_d).all()
    keys = [(s.sync_date, s.cinema_id, s.film_id) for s in all_snaps]
    assert len(keys) == len(set(keys))

    # If Film 1 is purged or no longer present today, its snapshot is cleaned up
    scraped_only_film2 = {
        "garden": [ShowtimeData(cinema="Cinema Garden", raw_title="Altro Film", date=sync_d, time=time(18, 0))],
        "citrigno": [ShowtimeData(cinema="citrigno", raw_title="Film 2", date=sync_d, time=time(19, 0))],
    }
    await run_sync(db, as_of_date=sync_d, cinemas=cinemas, scraper_results=scraped_only_film2)
    snaps_after = db.query(DailySnapshot).filter_by(sync_date=sync_d).all()
    film1_snaps = [s for s in snaps_after if s.film.raw_title == "Film 1"]
    assert len(film1_snaps) == 0


@pytest.mark.asyncio
async def test_scenario_avengers_scarta_spettacoli_precedenti_release_from(db):
    """Problem 1: 'DAL 16 DICEMBRE' extracts release_from, and sync discards earlier showtimes."""
    cinemas = [
        CinemaConfig(slug="garden", name="Cinema Garden", url="https://example.com", scraper="garden"),
    ]

    # Garden has showtimes on Oct 23, Oct 24 (phantom shows), and Dec 16 (real release)
    shows = [
        ShowtimeData(
            cinema="garden",
            raw_title="AVENGERS: DOOMSDAY - DAL 16 DICEMBRE",
            date=date(2026, 10, 23),
            time=time(21, 30),
            sala="Sala Garden",
        ),
        ShowtimeData(
            cinema="garden",
            raw_title="AVENGERS: DOOMSDAY - DAL 16 DICEMBRE",
            date=date(2026, 10, 24),
            time=time(18, 45),
            sala="Sala A",
        ),
        ShowtimeData(
            cinema="garden",
            raw_title="AVENGERS: DOOMSDAY - DAL 16 DICEMBRE",
            date=date(2026, 12, 16),
            time=time(21, 0),
            sala="Sala Garden",
        ),
    ]

    res = await run_sync(
        db,
        as_of_date=date(2026, 10, 18),
        cinemas=cinemas,
        scraper_results={"garden": shows},
    )

    film = db.query(Film).first()
    assert film.raw_title == "AVENGERS: DOOMSDAY"
    # Showtimes prior to Dec 16 were discarded: only 1 showtime remaining (Dec 16)
    saved_shows = db.query(Showtime).filter_by(film_id=film.id).all()
    assert len(saved_shows) == 1
    assert saved_shows[0].date == date(2026, 12, 16)

    # Film is strictly in the future compared to 18/10 -> in_uscita!
    assert film.status == "in_uscita"
    assert film.stato_programmazione == "in_uscita"


@pytest.mark.asyncio
async def test_scenario_due_sync_stesso_giorno_non_aumentano_assenza(db):
    """Problem 2A: Two syncs executed on the same day do not increase consecutive missing days."""
    cinemas = [
        CinemaConfig(slug="andromeda", name="Andromeda", url="https://example.com", scraper="stub"),
    ]

    # Day 1 (01/10): Film is seen
    day1_shows = [ShowtimeData(cinema="andromeda", raw_title="Il Gladiatore", date=date(2026, 10, 1), time=time(20, 0))]
    await run_sync(db, as_of_date=date(2026, 10, 1), cinemas=cinemas, scraper_results={"andromeda": day1_shows})

    film = db.query(Film).first()
    assert film.consecutive_missing_days == 0
    assert film.last_seen_date == date(2026, 10, 1)

    # Day 2 (02/10), Sync 1: Film is absent -> absence is 1 day
    other_shows = [ShowtimeData(cinema="andromeda", raw_title="Altro Film", date=date(2026, 10, 2), time=time(20, 0))]
    await run_sync(db, as_of_date=date(2026, 10, 2), cinemas=cinemas, scraper_results={"andromeda": other_shows})
    db.refresh(film)
    assert film.consecutive_missing_days == 1
    assert film.last_seen_date == date(2026, 10, 1)

    # Day 2 (02/10), Sync 2 (second sync on the SAME day):
    # Absence MUST remain 1 day, NOT increase to 2!
    await run_sync(db, as_of_date=date(2026, 10, 2), cinemas=cinemas, scraper_results={"andromeda": other_shows})
    db.refresh(film)
    assert film.consecutive_missing_days == 1
    assert film.status == "in_sala"


@pytest.mark.asyncio
async def test_scenario_sync_ogni_3_giorni_calcolo_corretto(db):
    """Problem 2B: A sync every 3 days calculates 3 calendar days of absence, not 1 sync."""
    cinemas = [
        CinemaConfig(slug="andromeda", name="Andromeda", url="https://example.com", scraper="stub"),
    ]

    # Day 1 (01/10): Film Regular and Film Event are both present
    day1_shows = [
        ShowtimeData(cinema="andromeda", raw_title="Film Regolare", date=date(2026, 10, 1), time=time(18, 0)),
        ShowtimeData(
            cinema="andromeda",
            raw_title="Film Evento Speciale",
            tags=["ANTEPRIMA"],
            date=date(2026, 10, 1),
            time=time(21, 0),
        ),
    ]
    await run_sync(db, as_of_date=date(2026, 10, 1), cinemas=cinemas, scraper_results={"andromeda": day1_shows})

    film_reg = db.query(Film).filter_by(raw_title="Film Regolare").one()
    film_evt = db.query(Film).filter_by(raw_title="Film Evento Speciale").one()
    assert is_event_film(film_reg) is False
    assert is_event_film(film_evt) is True

    # Next sync is on Day 4 (04/10) — 3 calendar days later without sync in between!
    day4_shows = [ShowtimeData(cinema="andromeda", raw_title="Altro Film", date=date(2026, 10, 4), time=time(18, 0))]
    await run_sync(db, as_of_date=date(2026, 10, 4), cinemas=cinemas, scraper_results={"andromeda": day4_shows})

    db.refresh(film_reg)
    db.refresh(film_evt)

    # Both films have 3 days of absence (04/10 - 01/10 = 3 days)
    assert film_reg.consecutive_missing_days == 3
    assert film_evt.consecutive_missing_days == 3

    # Film Event reached threshold 3 -> 'uscito'
    assert film_evt.status == "uscito"
    assert film_evt.left_theaters_date == date(2026, 10, 4)

    # Film Regular (threshold 7) -> still 'in_sala'
    assert film_reg.status == "in_sala"
    assert film_reg.left_theaters_date is None


@pytest.mark.asyncio
async def test_scenario_rimozione_euristica_programmazione_breve(db):
    """Problem 3: A film with a short run (<= 4 days) without explicit event tags is NOT an event."""
    cinemas = [
        CinemaConfig(slug="andromeda", name="Andromeda", url="https://example.com", scraper="stub"),
    ]

    # Film only programmed for 2 days, but has NO tags like EVENTO, film evento, ANTEPRIMA
    day1_shows = [
        ShowtimeData(cinema="andromeda", raw_title="Cineforum Normale", date=date(2026, 10, 1), time=time(18, 0)),
        ShowtimeData(cinema="andromeda", raw_title="Cineforum Normale", date=date(2026, 10, 2), time=time(18, 0)),
    ]
    await run_sync(db, as_of_date=date(2026, 10, 1), cinemas=cinemas, scraper_results={"andromeda": day1_shows})

    film = db.query(Film).first()
    # It must NOT be marked as an event
    assert is_event_film(film) is False
    assert film.is_event is False

    # Day 5 (05/10): 4 days after last seen date (01/10)
    day5_shows = [ShowtimeData(cinema="andromeda", raw_title="Altro Film", date=date(2026, 10, 5), time=time(18, 0))]
    await run_sync(db, as_of_date=date(2026, 10, 5), cinemas=cinemas, scraper_results={"andromeda": day5_shows})

    db.refresh(film)
    assert film.consecutive_missing_days == 4
    # Because threshold is 7 (not 3), it must STILL be in_sala!
    assert film.status == "in_sala"


@pytest.mark.asyncio
async def test_scenario_titolo_con_dal_non_scarta_spettacoli(db):
    """A title containing 'DAL' (e.g. 'LONTANO DAL MARE') keeps all its showtimes."""
    cinemas = [
        CinemaConfig(slug="andromeda", name="Andromeda", url="https://example.com", scraper="stub"),
    ]
    shows = [
        ShowtimeData(cinema="andromeda", raw_title="LONTANO DAL MARE", date=date(2026, 10, 23), time=time(18, 0)),
        ShowtimeData(cinema="andromeda", raw_title="PRADA 2", date=date(2026, 10, 23), time=time(21, 0)),
    ]
    res = await run_sync(db, as_of_date=date(2026, 10, 23), cinemas=cinemas, scraper_results={"andromeda": shows})

    assert res.showtimes == 2
    assert db.query(Showtime).count() == 2
    assert {f.status for f in db.query(Film).all()} == {"in_sala"}


@pytest.mark.asyncio
async def test_scenario_scraper_rotto_non_resuscita_film_usciti(db):
    """A failing scraper protects only its latest programming, not films that already left."""
    cinemas = [
        CinemaConfig(slug="andromeda", name="Andromeda", url="https://example.com", scraper="stub"),
    ]

    # 01/09: 'Vecchio Film' is playing
    day1 = [ShowtimeData(cinema="andromeda", raw_title="Vecchio Film", date=date(2026, 9, 1), time=time(18, 0))]
    await run_sync(db, as_of_date=date(2026, 9, 1), cinemas=cinemas, scraper_results={"andromeda": day1})

    # 21/09: only 'Altro Film' is playing -> 'Vecchio Film' missing for 20 days -> 'uscito'
    day2 = [ShowtimeData(cinema="andromeda", raw_title="Altro Film", date=date(2026, 9, 21), time=time(18, 0))]
    await run_sync(db, as_of_date=date(2026, 9, 21), cinemas=cinemas, scraper_results={"andromeda": day2})

    vecchio = db.query(Film).filter_by(normalized_title="vecchio film").one()
    altro = db.query(Film).filter_by(normalized_title="altro film").one()
    assert vecchio.status == "uscito"

    # 22/09: the scraper fails
    res = await run_sync(
        db,
        as_of_date=date(2026, 9, 22),
        cinemas=cinemas,
        scraper_errors={"andromeda": RuntimeError("timeout")},
    )

    db.refresh(vecchio)
    db.refresh(altro)
    # 'Vecchio Film' stays 'uscito' with its original exit date
    assert vecchio.status == "uscito"
    assert vecchio.left_theaters_date == date(2026, 9, 21)
    assert not any(c.change_type == "reappeared" for c in res.status_changes)
    # 'Altro Film' (latest programming of the failed cinema) is still protected
    assert altro.status == "in_sala"
    assert altro.consecutive_missing_days == 0
