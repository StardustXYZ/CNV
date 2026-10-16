"""Offline unit tests for 18tickets parser using saved HTML fixtures."""

from __future__ import annotations

from datetime import date, time
from pathlib import Path

import pytest

from app.scrapers.eighteen_tickets import (
    clean_title,
    parse_coming_soon_html,
    parse_showtimes_html,
)

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture()
def andromeda_html() -> str:
    return (FIXTURES_DIR / "andromeda_river.html").read_text(encoding="utf-8")


@pytest.fixture()
def citrigno_html() -> str:
    return (FIXTURES_DIR / "citrigno.html").read_text(encoding="utf-8")


@pytest.fixture()
def unical_html() -> str:
    return (FIXTURES_DIR / "unical.html").read_text(encoding="utf-8")


@pytest.fixture()
def italia_html() -> str:
    return (FIXTURES_DIR / "italia.html").read_text(encoding="utf-8")


@pytest.fixture()
def andromeda_coming_soon_html() -> str:
    return (FIXTURES_DIR / "andromeda_river_coming_soon.html").read_text(encoding="utf-8")


@pytest.fixture()
def citrigno_coming_soon_html() -> str:
    return (FIXTURES_DIR / "citrigno_coming_soon.html").read_text(encoding="utf-8")


def test_andromeda_river_schedule(andromeda_html: str):
    base_url = "https://zumpano.andromeda.andromedacinema.it/"
    items = parse_showtimes_html(andromeda_html, cinema_slug="andromeda-river", base_url=base_url)

    # 11 distinct films and 71 total showtimes
    unique_titles = {clean_title(item.raw_title) for item in items}
    assert len(unique_titles) == 11
    assert len(items) == 71

    # Verify every item has required fields populated
    for item in items:
        assert item.cinema == "andromeda-river"
        assert item.raw_title
        assert isinstance(item.date, date)
        assert isinstance(item.time, time)
        assert item.source_url.startswith("https://")

    # Verify advance pre-sales (e.g. December 2026)
    december_items = [it for it in items if it.date.month == 12]
    assert len(december_items) == 20  # 19 Avengers + 1 Dune
    avengers_dec = [it for it in december_items if "AVENGERS" in it.raw_title]
    assert len(avengers_dec) == 19
    dune_dec = [it for it in december_items if "DUNE" in it.raw_title]
    assert len(dune_dec) == 1
    assert dune_dec[0].date == date(2026, 12, 15)
    assert "#ANTEPRIMA" in dune_dec[0].tags

    # Verify labels / tags extraction
    trainspotting_items = [it for it in items if "TRAINSPOTTING" in it.raw_title]
    assert len(trainspotting_items) == 3
    for it in trainspotting_items:
        assert "14+" in it.tags
        assert "EVENTO 8" in it.tags

    carlo_acutis = [it for it in items if "CARLO ACUTIS" in it.raw_title]
    assert len(carlo_acutis) == 3
    for it in carlo_acutis:
        assert "EVENTO 10" in it.tags


def test_citrigno_schedule(citrigno_html: str):
    base_url = "https://citrigno.cosenzacinema.18tickets.it/"
    items = parse_showtimes_html(citrigno_html, cinema_slug="citrigno", base_url=base_url)

    unique_titles = {clean_title(item.raw_title) for item in items}
    assert len(unique_titles) == 4
    assert len(items) == 31

    # Check December pre-sales in Citrigno (Avengers: Doomsday)
    december_items = [it for it in items if it.date.month == 12]
    assert len(december_items) == 10
    for it in december_items:
        assert "AVENGERS" in it.raw_title
        assert it.source_url == "https://citrigno.cosenzacinema.18tickets.it/film/98245"


def test_unical_schedule(unical_html: str):
    base_url = "https://unical.cosenzacinema.18tickets.it/"
    items = parse_showtimes_html(unical_html, cinema_slug="unical", base_url=base_url)

    unique_titles = {clean_title(item.raw_title) for item in items}
    assert len(unique_titles) == 4
    assert len(items) == 21

    trainspotting = [it for it in items if "TRAINSPOTTING" in it.raw_title]
    assert len(trainspotting) == 3
    assert "EVENTO" in trainspotting[0].tags


def test_italia_schedule(italia_html: str):
    base_url = "https://cinemateatroitalia.cosenzacinema.18tickets.it/"
    items = parse_showtimes_html(italia_html, cinema_slug="italia-tieri", base_url=base_url)

    unique_titles = {clean_title(item.raw_title) for item in items}
    assert len(unique_titles) == 2
    assert len(items) == 11

    carlo_acutis = [it for it in items if "CARLO ACUTIS" in it.raw_title]
    assert len(carlo_acutis) == 4
    assert any("EVENTO" in t for t in carlo_acutis[0].tags)


def test_andromeda_coming_soon(andromeda_coming_soon_html: str):
    base_url = "https://zumpano.andromeda.andromedacinema.it/coming_soon"
    items = parse_coming_soon_html(andromeda_coming_soon_html, cinema_slug="andromeda-river", base_url=base_url)

    assert len(items) == 35

    first = items[0]
    assert "SE AMI QUALCUNO DILLO" in first.raw_title
    assert clean_title(first.raw_title) == "SE AMI QUALCUNO DILLO"
    assert first.release_date == date(2026, 10, 18)
    assert first.tags == ["OSPITI IN SALA"]
    assert first.source_url == "https://zumpano.andromeda.andromedacinema.it/film/83216"


def test_citrigno_coming_soon(citrigno_coming_soon_html: str):
    base_url = "https://citrigno.cosenzacinema.18tickets.it/coming_soon"
    items = parse_coming_soon_html(citrigno_coming_soon_html, cinema_slug="citrigno", base_url=base_url)

    assert len(items) == 1
    assert "AVENGERS" in items[0].raw_title
    assert items[0].release_date == date(2026, 12, 15)
    assert items[0].source_url == "https://citrigno.cosenzacinema.18tickets.it/film/98245"

